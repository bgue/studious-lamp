// Format detection and the single entry point of the readers.

import type { PointCloudData, ProgressFn } from '../types';
import { PointCloudError } from '../types';
import { LAZ_MESSAGE, isLas, readLas } from './las';
import { readPcd } from './pcd';
import { readPly } from './ply';
import { readText } from './text';

export const POINTCLOUD_EXTENSIONS = ['.ply', '.pcd', '.xyz', '.pts', '.txt', '.las'] as const;
/** Extensions the drop handler claims: the readable ones plus .laz, so the drop produces a clear message. */
export const DROP_EXTENSIONS = [...POINTCLOUD_EXTENSIONS, '.laz'] as const;

export function extensionOf(name: string): string {
  const i = name.lastIndexOf('.');
  return i < 0 ? '' : name.slice(i).toLowerCase();
}

export function isPointCloudName(name: string): boolean {
  return (DROP_EXTENSIONS as readonly string[]).includes(extensionOf(name));
}

export type CloudFormat = 'las' | 'ply' | 'pcd' | 'xyz' | 'pts' | 'txt';

/** Decide the format from the leading bytes first, then from the extension. */
export function detectFormat(bytes: Uint8Array, name: string): CloudFormat {
  if (isLas(bytes)) return 'las';
  const head = new TextDecoder().decode(bytes.subarray(0, 64));
  if (/^ply\r?\n/.test(head)) return 'ply';
  const h = head.trimStart();
  if (/^(# \.PCD|VERSION|FIELDS)/i.test(h)) return 'pcd';
  const ext = extensionOf(name);
  if (ext === '.las') return 'las'; // fails in readLas with "missing LASF"
  if (ext === '.ply') return 'ply';
  if (ext === '.pcd') return 'pcd';
  if (ext === '.pts') return 'pts';
  if (ext === '.xyz') return 'xyz';
  return 'txt';
}

export function parsePointCloud(data: ArrayBuffer | Uint8Array, name: string, onProgress?: ProgressFn): PointCloudData {
  const bytes = data instanceof Uint8Array ? data : new Uint8Array(data);
  if (extensionOf(name) === '.laz') throw new PointCloudError(LAZ_MESSAGE);
  if (bytes.length === 0) throw new PointCloudError(`${name} is empty`);
  switch (detectFormat(bytes, name)) {
    case 'las': return readLas(bytes, name, onProgress);
    case 'ply': return readPly(bytes, name, onProgress);
    case 'pcd': return readPcd(bytes, name, onProgress);
    case 'pts': return readText(bytes, name, 'pts', onProgress);
    case 'xyz': return readText(bytes, name, 'xyz', onProgress);
    default: return readText(bytes, name, 'txt', onProgress);
  }
}

export { LAZ_MESSAGE };
