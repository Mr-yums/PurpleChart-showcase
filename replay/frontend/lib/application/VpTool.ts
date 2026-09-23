/**
 * PurpleReplay v2 — outil « VP de mesure »
 * Pont entre la barre d'outils (bouton Tracer / Effacer) et l'overlay monté dans le graphique.
 */
import { writable } from 'svelte/store';
interface VolumeRangeTool {
 readonly armed: boolean;
 arm(): void;
 clearAll(): void;
 blocksChart(x: number, y: number): boolean;
}

class VpTool {
	readonly armed = writable(false);
	private range: VolumeRangeTool | null = null;
	bind(r: VolumeRangeTool): void { this.range = r; }
	unbind(): void { this.range = null; this.armed.set(false); }
	arm(): void { if (this.range) { this.range.arm(); this.armed.set(true); } }
	disarmed(): void { this.armed.set(false); }
	clear(): void { this.range?.clearAll(); }
	blocks(x: number, y: number): boolean { return this.range?.blocksChart(x, y) ?? false; }
	get isArmed(): boolean { return this.range?.armed ?? false; }
}
export const vpTool = new VpTool();
