/**
 * PurpleReplay v2 — client HTTP typé (même patron que PurpleChart v2)
 * Same-origin : Vite proxifie /api vers le backend FastAPI.
 */
export class ApiError extends Error {
	constructor(public status: number, public detail: string) {
		super(`API ${status}: ${detail}`);
		this.name = 'ApiError';
	}
}

export class ApiClient {
    private active = true;
    private pending = new Set<AbortController>();
    activate(): void { this.active = true; }
    suspend(): void { this.active = false; for (const c of this.pending) c.abort(); this.pending.clear(); }

	constructor(private baseUrl = '') {}

	private async request<T>(method: string, path: string, body?: unknown, timeoutMs = 180000): Promise<T> {
        if (!this.active) throw new ApiError(409,'Replay arrêté');
		const controller = new AbortController();
        this.pending.add(controller);
		const timer = setTimeout(() => controller.abort(), timeoutMs);
		try {
			const response = await fetch(`${this.baseUrl}/api${path}`, {
				method,
				headers: { 'Content-Type': 'application/json' },
				body: body === undefined ? undefined : JSON.stringify(body),
				signal: controller.signal
			});
			const data = await response.json().catch(() => ({}));
			if (!response.ok) throw new ApiError(response.status, data.detail || data.error || response.statusText);
			return data as T;
		} finally {
            this.pending.delete(controller);
			clearTimeout(timer);
		}
	}

	get<T>(path: string) { return this.request<T>('GET', path); }
	post<T>(path: string, body?: unknown) { return this.request<T>('POST', path, body ?? {}); }
}

export const api = new ApiClient();

export function qs(params: Record<string, string | number | undefined | null>): string {
	const parts: string[] = [];
	for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null) parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`);
	return parts.length ? '?' + parts.join('&') : '';
}
