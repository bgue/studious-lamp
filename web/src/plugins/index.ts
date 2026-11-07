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
import { sectionPlugin } from './section';
import { gizmoPlugin } from './gizmo';
import { cleanupPlugin } from './cleanup';
import { hoverInfoPlugin } from './hoverInfo';
import { presetsPlugin } from './presets';
import { keymapPlugin } from './keymap';
import { toolbarPlugin } from './toolbar';
import { penetrationsPlugin } from './penetrations';
import { measurePlugin } from './measure';
import { bcfPlugin } from './bcf';
import { pointcloudPlugin } from './pointcloud';
import { xrPlugin } from './xr';
import { bootPlugin } from './boot';
import { helpPlugin } from './help';
import { panelDockPlugin } from './panelDock';
import { exportParamsPlugin } from './exportParams';
import { viewsPlugin } from './views';
import { topBarPlugin } from './topBar';
import { awesomeBarPlugin } from './awesomeBar';

// views after exportParams (its factory snapshot is the state after the first model and any #p= link) and before boot.
// help runs after every panel-building plugin so it can see all controls; panelDock last so it wraps the finished panel.
// topBar first: it creates the bar and the #xray-topbar-search host that the awesomeBar plugin mounts into, and its onModel
// takes the factory settings hash before any other plugin changes the state.
export const PLUGINS: AppPlugin[] = [topBarPlugin, fileLoaderPlugin, classStylesPlugin, sidebarPlugin, cinematicPlugin, oitPlugin, viewModesPlugin, imagingPlugin, sectionPlugin, gizmoPlugin, cleanupPlugin, hoverInfoPlugin, presetsPlugin, penetrationsPlugin, measurePlugin, bcfPlugin, pointcloudPlugin, xrPlugin, toolbarPlugin, keymapPlugin, exportParamsPlugin, viewsPlugin, helpPlugin, panelDockPlugin, awesomeBarPlugin, bootPlugin];
