// Frame sinks of the video export: the WebCodecs encoder with a muxer (mediabunny, loaded on first use so the main bundle does not
// grow) for MP4 and WebM, and a PNG image sequence in a store-only zip.

import type { CanvasLike, ExportFile, FrameSink } from './frames';
import type { EncoderChoice } from './encoder';
import { StoreZip, frameFileName } from './zip';

export interface VideoSinkOptions {
  choice: EncoderChoice;
  fps: number;
  bitrate: number;
}

const CODEC_LABEL = { avc: 'H.264', vp9: 'VP9', vp8: 'VP8' } as const;

/** MP4 (H.264) or WebM (VP9 or VP8) through WebCodecs and mediabunny. */
export class VideoFileSink implements FrameSink {
  private output: import('mediabunny').Output | null = null;
  private source: import('mediabunny').CanvasSource | null = null;
  private target: import('mediabunny').BufferTarget | null = null;
  private frames = 0;
  private packets = 0;

  constructor(private readonly o: VideoSinkOptions) {}

  /** Encoded packets so far (a check that every frame came out). */
  get packetCount(): number {
    return this.packets;
  }

  async start(canvas: CanvasLike): Promise<void> {
    const { Output, Mp4OutputFormat, WebMOutputFormat, BufferTarget, CanvasSource } = await import('mediabunny');
    const { container, codec } = this.o.choice;
    this.target = new BufferTarget();
    this.output = new Output({
      format: container === 'mp4' ? new Mp4OutputFormat({ fastStart: 'in-memory' }) : new WebMOutputFormat(),
      target: this.target,
    });
    this.source = new CanvasSource(canvas as unknown as HTMLCanvasElement, {
      codec,
      bitrate: this.o.bitrate,
      keyFrameInterval: 2,
      onEncodedPacket: () => {
        this.packets++;
      },
    });
    this.output.addVideoTrack(this.source, { frameRate: this.o.fps });
    await this.output.start();
  }

  async add(_canvas: CanvasLike, _index: number, time: number, duration: number): Promise<void> {
    if (!this.source) throw new Error('The encoder is not started');
    await this.source.add(time, duration);
    this.frames++;
  }

  async finish(): Promise<ExportFile> {
    if (!this.output || !this.target) throw new Error('The encoder is not started');
    await this.output.finalize();
    const buf = this.target.buffer;
    if (!buf) throw new Error('The encoder produced no data');
    const { container, codec } = this.o.choice;
    const mime = container === 'mp4' ? 'video/mp4' : 'video/webm';
    return { blob: new Blob([buf], { type: mime }), mime, extension: container, frames: this.frames, description: `${CODEC_LABEL[codec]} in ${container.toUpperCase()}` };
  }

  async cancel(): Promise<void> {
    const out = this.output;
    this.output = null;
    this.source = null;
    this.target = null;
    if (out && out.state !== 'finalized' && out.state !== 'canceled') {
      try {
        await out.cancel();
      } catch {
        /* already torn down */
      }
    }
  }
}

/** PNG frames in a zip: frame-000001.png and so on. */
export class PngZipSink implements FrameSink {
  private zip: StoreZip | null = null;
  private frames = 0;

  constructor(private readonly toPng: (canvas: CanvasLike) => Promise<Uint8Array>, private readonly prefix = 'frame') {}

  async start(): Promise<void> {
    this.zip = new StoreZip();
  }

  async add(canvas: CanvasLike, index: number): Promise<void> {
    if (!this.zip) throw new Error('The zip is not started');
    this.zip.add(frameFileName(index, this.prefix), await this.toPng(canvas));
    this.frames++;
  }

  async finish(): Promise<ExportFile> {
    if (!this.zip) throw new Error('The zip is not started');
    const blob = this.zip.finish();
    return { blob, mime: 'application/zip', extension: 'zip', frames: this.frames, description: 'PNG image sequence in a zip' };
  }

  async cancel(): Promise<void> {
    this.zip = null;
  }
}

export function canvasToPng(canvas: CanvasLike): Promise<Uint8Array> {
  const c = canvas as unknown as HTMLCanvasElement;
  return new Promise((resolve, reject) => {
    c.toBlob((b) => {
      if (!b) return reject(new Error('A frame could not be written as PNG'));
      void b.arrayBuffer().then((ab) => resolve(new Uint8Array(ab)), reject);
    }, 'image/png');
  });
}
