// Canvas overlay commun : dimensionné au host (dpr), redessiné au zoom/scroll/resize, une frame max par rAF.
import type { IChartApi } from 'lightweight-charts';

export class OverlayCanvas {
	readonly canvas: HTMLCanvasElement;
	readonly ctx: CanvasRenderingContext2D;
	width = 0;
	height = 0;
	private raf = 0;
	private disposed = false; // [Sol]
	private ro: ResizeObserver | null = null;
	private offRange: (() => void) | null = null;

	constructor(readonly host: HTMLElement, readonly chart: IChartApi, private draw: (ctx: CanvasRenderingContext2D, w: number, h: number) => void, zIndex = 4) {
		this.canvas = document.createElement('canvas');
		this.canvas.style.cssText = `position:absolute;left:0;top:0;pointer-events:none;z-index:${zIndex};`;
		this.ctx = this.canvas.getContext('2d')!;
		if (getComputedStyle(host).position === 'static') host.style.position = 'relative';
		host.appendChild(this.canvas);
		this.resize();
		this.ro = new ResizeObserver(() => { this.resize(); this.schedule(); });
		this.ro.observe(host);
		const onRange = () => this.schedule();
		chart.timeScale().subscribeVisibleLogicalRangeChange(onRange);
		this.offRange = () => chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRange);
	}

	resize(): void {
		const r = this.host.getBoundingClientRect();
		const dpr = window.devicePixelRatio || 1;
		this.width = r.width; this.height = r.height;
		this.canvas.width = Math.round(r.width * dpr); this.canvas.height = Math.round(r.height * dpr);
		this.canvas.style.width = r.width + 'px'; this.canvas.style.height = r.height + 'px';
		this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
	}

	schedule(): void {
		if (this.disposed || this.raf) return;
		this.raf = requestAnimationFrame(() => { this.raf = 0; this.render(); });
	}

	render(): void {
		if (!this.width || !this.height) return;
		this.ctx.clearRect(0, 0, this.width, this.height);
		this.draw(this.ctx, this.width, this.height);
	}

	clear(): void { this.ctx.clearRect(0, 0, this.width, this.height); }

	dispose(): void {
		this.disposed = true;
		if (this.raf) cancelAnimationFrame(this.raf);
		this.ro?.disconnect();
		this.offRange?.();
		this.canvas.remove();
	}
}
