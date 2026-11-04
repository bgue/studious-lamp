// Plugin registry. Each plugin lives in its own module under src/plugins and is
// registered here. Order matters: install/onModel/onFrame hooks run in this order.
import type { AppPlugin } from '../app';
import { classStylesPlugin } from './classStyles';
import { sidebarPlugin } from './sidebar';
import { cinematicPlugin } from './cinematic';
import { oitPlugin } from './oit';
import { fileLoaderPlugin } from './fileLoader';
import { viewModesPlugin } from './viewModes';
import { imagingPlugin } from './imaging';
import { cleanupPlugin } from './cleanup';
import { hoverInfoPlugin } from './hoverInfo';
import { presetsPlugin } from './presets';
import { keymapPlugin } from './keymap';
import { helpPlugin } from './help';
import { panelDockPlugin } from './panelDock';
import { exportParamsPlugin } from './exportParams';

// help runs after every panel-building plugin so it can see all controls; panelDock last so it wraps the finished panel.
export const PLUGINS: AppPlugin[] = [fileLoaderPlugin, classStylesPlugin, sidebarPlugin, cinematicPlugin, oitPlugin, viewModesPlugin, imagingPlugin, cleanupPlugin, hoverInfoPlugin, presetsPlugin, keymapPlugin, exportParamsPlugin, helpPlugin, panelDockPlugin];
