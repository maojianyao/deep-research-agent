import { defineStore } from "pinia";
import { markRaw } from "vue";
import { api, apiUrl } from "../lib/api";

const terminal = new Set(["completed", "failed", "needs_human_review", "cancelled", "paused"]);

export const useResearchStore = defineStore("research", {
  state: () => ({
    runs: [], total: 0, page: 1, pageSize: 20, search: "", statusFilter: "",
    runId: null, run: null, eventSequence: 0, eventSource: null, pollTimer: null,
    listTimer: null, connection: "connecting", loading: false, error: "",
  }),
  getters: {
    isActive: (state) => Boolean(state.run && !terminal.has(state.run.status)),
    pageCount: (state) => Math.max(1, Math.ceil(state.total / state.pageSize)),
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
      await this.refreshRun();
      if (this.isActive) this.connectSse();
    },
    async refreshRun() {
      if (!this.runId) return;
      try {
        this.run = await api(`/research-runs/${encodeURIComponent(this.runId)}`);
        const latest = Math.max(0, ...(this.run.events || []).map((event) => event.sequence));
        this.eventSequence = Math.max(this.eventSequence, latest);
      } catch (error) { this.error = error.message; }
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
    async createRun(userRequest, maxIterations) {
      const result = await api("/research-runs", {
        method: "POST",
        body: JSON.stringify({ user_request: userRequest, max_iterations: maxIterations }),
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
    selectStatus(value) { this.statusFilter = value; this.page = 1; this.loadRuns(); },
    selectPage(value) { this.page = value; this.loadRuns(); },
    clearRun() {
      this.closeLiveUpdates();
      this.runId = null;
      this.run = null;
      this.eventSequence = 0;
      this.connection = "online";
    },
  },
});
