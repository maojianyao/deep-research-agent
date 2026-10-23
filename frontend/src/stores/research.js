import { defineStore } from "pinia";
import { markRaw } from "vue";
import { api, apiUrl } from "../lib/api";

const terminal = new Set(["completed", "failed", "needs_human_review", "cancelled", "paused"]);

export const useResearchStore = defineStore("research", {
  state: () => ({
    runs: [], total: 0, page: 1, pageSize: 20, search: "", statusFilter: "",
    summary: { total: 0, active: 0, completed: 0, needs_human_review: 0 },
    runId: null, run: null, eventSequence: 0, eventSource: null, pollTimer: null,
    listTimer: null, connection: "connecting", loading: false, error: "",
    followUps: [], selectedFollowUpId: null,
    followUpEventSource: null, followUpReconnectTimer: null, followUpStreamThreadId: null,
  }),
  getters: {
    isActive: (state) => Boolean(state.run && !terminal.has(state.run.status)),
    pageCount: (state) => Math.max(1, Math.ceil(state.total / state.pageSize)),
    selectedFollowUp: (state) => state.followUps.find(
      (item) => item.id === state.selectedFollowUpId
    ) || null,
    selectedFollowUpBusy: (state) => Boolean(state.followUps.find(
      (item) => item.id === state.selectedFollowUpId
    )?.messages.some(
      (message) => message.role === "assistant" && message.status === "generating"
    )),
  },
  actions: {
    async loadRuns() {
      this.loading = true;
      const params = new URLSearchParams({ page: this.page, page_size: this.pageSize });
      if (this.statusFilter) params.set("status", this.statusFilter);
      if (this.search.trim()) params.set("search", this.search.trim());
      try {
        const data = await api(`/research-runs?${params}`);
        this.runs = data.items;
        this.total = data.total;
        this.summary = data.summary || this.summary;
        this.connection = "online";
        this.error = "";
        if (this.page > this.pageCount) { this.page = this.pageCount; return this.loadRuns(); }
      } catch (error) {
        this.connection = "offline";
        this.error = error.message;
      } finally { this.loading = false; }
    },
    setSearch(value) {
      this.search = value;
      this.page = 1;
      clearTimeout(this.listTimer);
      this.listTimer = setTimeout(() => this.loadRuns(), 250);
    },
    async openRun(runId) {
      this.closeLiveUpdates();
      this.runId = runId;
      this.run = null;
      this.eventSequence = 0;
      this.followUps = [];
      this.selectedFollowUpId = null;
      const error = await this.refreshRun();
      if (this.run?.status === "completed" && this.run.report) await this.loadFollowUps();
      if (this.isActive) this.connectSse();
      return error;
    },
    async refreshRun() {
      if (!this.runId) return null;
      try {
        this.run = await api(`/research-runs/${encodeURIComponent(this.runId)}`);
        const latest = Math.max(0, ...(this.run.events || []).map((event) => event.sequence));
        this.eventSequence = Math.max(this.eventSequence, latest);
        return null;
      } catch (error) {
        this.error = error.message;
        return error.message;
      }
    },
    connectSse() {
      if (!this.runId || !this.isActive) return;
      this.closeLiveUpdates();
      this.connection = "stream";
      const url = apiUrl(`/research-runs/${encodeURIComponent(this.runId)}/events?after_sequence=${this.eventSequence}`);
      const source = markRaw(new EventSource(url));
      this.eventSource = source;
      source.onopen = () => { this.connection = "stream"; };
      source.addEventListener("progress", async (event) => {
        try {
          const progress = JSON.parse(event.data);
          if (progress.id !== this.runId) return;
          this.eventSequence = Math.max(this.eventSequence, Number(event.lastEventId) || 0,
            ...(progress.events || []).map((item) => item.sequence));
          await this.refreshRun();
          if (terminal.has(progress.status)) {
            this.closeLiveUpdates();
            this.connection = "online";
            this.loadRuns();
          }
        } catch { this.startPolling(); }
      });
      source.onerror = () => {
        source.close();
        if (this.eventSource === source) this.eventSource = null;
        this.startPolling();
      };
    },
    startPolling() {
      if (!this.runId || this.pollTimer || !this.isActive) return;
      this.connection = "polling";
      this.pollTimer = setInterval(async () => {
        if (!this.runId) return;
        try {
          const progress = await api(`/research-runs/${encodeURIComponent(this.runId)}/progress?after_sequence=${this.eventSequence}`);
          this.eventSequence = Math.max(this.eventSequence, ...(progress.events || []).map((item) => item.sequence));
          await this.refreshRun();
          if (!this.isActive) {
            this.closeLiveUpdates();
            this.connection = "online";
            this.loadRuns();
          }
        } catch (error) { this.error = error.message; }
      }, 3000);
    },
    closeLiveUpdates() {
      this.eventSource?.close();
      this.eventSource = null;
      if (this.pollTimer) clearInterval(this.pollTimer);
      this.pollTimer = null;
    },
    async createRun(userRequest, maxIterations, reportLanguage = "") {
      const result = await api("/research-runs", {
        method: "POST",
        body: JSON.stringify({
          user_request: userRequest,
          max_iterations: maxIterations,
          report_language: reportLanguage || null,
        }),
      });
      await this.loadRuns();
      await this.openRun(result.id);
      return result;
    },
    async runAction(action) {
      if (!this.runId) return;
      await api(`/research-runs/${encodeURIComponent(this.runId)}/${action}`, { method: "POST" });
      await this.refreshRun();
      if (this.isActive) this.connectSse();
      await this.loadRuns();
    },
    async deleteRun(runId) {
      await api(`/research-runs/${encodeURIComponent(runId)}`, { method: "DELETE" });
      if (this.runId === runId) this.clearRun();
      if (this.runs.length === 1 && this.page > 1) this.page -= 1;
      await this.loadRuns();
    },
    async citation(referenceId) {
      if (!this.runId) return null;
      return api(`/research-runs/${encodeURIComponent(this.runId)}/references/${encodeURIComponent(referenceId)}`);
    },
    async loadFollowUps() {
      if (!this.runId) return;
      const data = await api(`/research-runs/${encodeURIComponent(this.runId)}/follow-ups`);
      this.followUps = data.items;
      this.selectedFollowUpId = this.followUps.find(
        (item) => item.is_minimized === false
      )?.id || null;
      if (this.selectedFollowUp) this.connectFollowUpStream(this.selectedFollowUp);
    },
    async createFollowUp(anchor, question) {
      if (!this.runId) return null;
      const thread = await api(`/research-runs/${encodeURIComponent(this.runId)}/follow-ups`, {
        method: "POST",
        body: JSON.stringify({ anchor, question }),
      });
      this.followUps.forEach((item) => { item.is_minimized = true; });
      this.upsertFollowUp(thread);
      this.selectedFollowUpId = thread.id;
      this.connectFollowUpStream(thread);
      return thread;
    },
    async appendFollowUp(question) {
      if (!this.runId || !this.selectedFollowUpId) return null;
      const thread = await api(
        `/research-runs/${encodeURIComponent(this.runId)}/follow-ups/${encodeURIComponent(this.selectedFollowUpId)}/questions`,
        { method: "POST", body: JSON.stringify({ question }) },
      );
      this.upsertFollowUp(thread);
      this.connectFollowUpStream(thread);
      return thread;
    },
    async retryFollowUp(messageId) {
      if (!this.runId || !this.selectedFollowUpId) return null;
      const thread = await api(
        `/research-runs/${encodeURIComponent(this.runId)}/follow-ups/${encodeURIComponent(this.selectedFollowUpId)}/messages/${encodeURIComponent(messageId)}/retry`,
        { method: "POST" },
      );
      this.upsertFollowUp(thread);
      this.connectFollowUpStream(thread);
      return thread;
    },
    async expandFollowUp(threadId) {
      if (!this.runId) return null;
      const data = await api(
        `/research-runs/${encodeURIComponent(this.runId)}/follow-ups/${encodeURIComponent(threadId)}/state`,
        { method: "POST", body: JSON.stringify({ minimized: false }) },
      );
      this.replaceFollowUps(data.items);
      this.selectedFollowUpId = threadId;
      if (this.selectedFollowUp) this.connectFollowUpStream(this.selectedFollowUp);
      return this.selectedFollowUp;
    },
    async minimizeFollowUp() {
      if (!this.runId || !this.selectedFollowUpId) return null;
      const data = await api(
        `/research-runs/${encodeURIComponent(this.runId)}/follow-ups/${encodeURIComponent(this.selectedFollowUpId)}/state`,
        { method: "POST", body: JSON.stringify({ minimized: true }) },
      );
      this.replaceFollowUps(data.items);
      this.selectedFollowUpId = null;
      this.closeFollowUpStream();
      return data.items;
    },
    async deleteFollowUp(threadId = null) {
      const target = threadId || this.selectedFollowUpId;
      if (!this.runId || !target) return;
      await api(
        `/research-runs/${encodeURIComponent(this.runId)}/follow-ups/${encodeURIComponent(target)}`,
        { method: "DELETE" },
      );
      const index = this.followUps.findIndex((item) => item.id === target);
      if (index >= 0) this.followUps.splice(index, 1);
      if (this.selectedFollowUpId === target) {
        this.selectedFollowUpId = null;
        this.closeFollowUpStream();
      }
    },
    selectFollowUp(threadId) {
      this.closeFollowUpStream();
      this.selectedFollowUpId = threadId;
      if (this.selectedFollowUp) this.connectFollowUpStream(this.selectedFollowUp);
    },
    upsertFollowUp(thread) {
      const index = this.followUps.findIndex((item) => item.id === thread.id);
      if (index < 0) this.followUps.push(thread);
      else this.followUps.splice(index, 1, thread);
    },
    replaceFollowUps(items) {
      this.followUps.splice(0, this.followUps.length, ...items);
    },
    connectFollowUpStream(thread = this.selectedFollowUp) {
      this.closeFollowUpStream();
      if (!thread?.messages?.some(
        (message) => message.role === "assistant" && message.status === "generating"
      )) return;
      this.followUpStreamThreadId = thread.id;
      const cursor = Number(thread.stream_cursor || 0);
      const source = markRaw(new EventSource(apiUrl(
        `/research-runs/${encodeURIComponent(this.runId)}/follow-ups/${encodeURIComponent(thread.id)}/events?after_sequence=${cursor}`
      )));
      this.followUpEventSource = source;
      source.addEventListener("follow-up", (event) => this.applyFollowUpEvent(event));
      source.onerror = () => {
        if (this.followUpEventSource !== source) return;
        source.close();
        this.followUpEventSource = null;
        const threadId = this.followUpStreamThreadId;
        clearTimeout(this.followUpReconnectTimer);
        this.followUpReconnectTimer = setTimeout(() => {
          const current = this.followUps.find((item) => item.id === threadId);
          if (current) this.connectFollowUpStream(current);
        }, 250);
      };
    },
    applyFollowUpEvent(event) {
      try {
        const data = JSON.parse(event.data);
        const thread = this.followUps.find((item) => item.id === data.thread_id);
        if (!thread || Number(data.sequence) <= Number(thread.stream_cursor || 0)) return;
        thread.stream_cursor = Number(data.sequence);
        const message = thread.messages.find((item) => item.id === data.message_id);
        if (message) {
          if (data.type === "delta") message.content = `${message.content || ""}${data.content || ""}`;
          if (data.status) message.status = data.status;
          if (data.error_code !== undefined) message.error_code = data.error_code;
          if (data.error_message !== undefined) message.error_message = data.error_message;
        }
        if (["completed", "failed", "interrupted"].includes(data.type)) {
          this.closeFollowUpStream();
        }
      } catch {
        this.error = "追问流数据格式无效";
      }
    },
    closeFollowUpStream() {
      this.followUpEventSource?.close();
      this.followUpEventSource = null;
      this.followUpStreamThreadId = null;
      clearTimeout(this.followUpReconnectTimer);
      this.followUpReconnectTimer = null;
    },
    selectStatus(value) { this.statusFilter = value; this.page = 1; this.loadRuns(); },
    selectPage(value) { this.page = value; this.loadRuns(); },
    clearRun() {
      this.closeLiveUpdates();
      this.runId = null;
      this.run = null;
      this.eventSequence = 0;
      this.followUps = [];
      this.selectedFollowUpId = null;
      this.closeFollowUpStream();
      this.connection = "online";
    },
  },
});
