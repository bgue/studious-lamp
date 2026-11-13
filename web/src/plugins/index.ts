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
import { pointerModePlugin } from './pointerMode';
import { undoPlugin } from './undo';
import { cleanupPlugin } from './cleanup';
import { classifyPlugin } from './classify';
import { hoverInfoPlugin } from './hoverInfo';
import { presetsPlugin } from './presets';
import { keymapPlugin } from './keymap';
import { toolbarPlugin } from './toolbar';
import { penetrationsPlugin } from './penetrations';
import { measurePlugin } from './measure';
import { bcfPlugin } from './bcf';
import { markupPlugin } from './markup';
import { pointcloudPlugin } from './pointcloud';
import { xrPlugin } from './xr';
import { bootPlugin } from './boot';
import { helpPlugin } from './help';
import { panelDockPlugin } from './panelDock';
import { exportParamsPlugin } from './exportParams';
import { viewsPlugin } from './views';
import { issuesPlugin } from './issues';
import { sheetsPlugin } from './sheets';
import { topBarPlugin } from './topBar';
import { awesomeBarPlugin } from './awesomeBar';

// sheets right after issues (it adds the Sheets segment to the Issues panel and joins its controller).
// issues after views (its sidebar tab follows Views) and after bcf and markup (it joins their controllers).
// views after exportParams (its factory snapshot is the state after the first model and any #p= link) and before boot.
// pointerMode before gizmo (its toggle lives there); undo last: its onModel runs after boot has applied the link, preset and camera,
// so what boot changed is the starting state, not history.
// help runs after every panel-building plugin so it can see all controls; panelDock last so it wraps the finished panel.
// topBar first: it creates the bar and the #xray-topbar-search host that the awesomeBar plugin mounts into, and its onModel
// takes the factory settings hash before any other plugin changes the state.
export const PLUGINS: AppPlugin[] = [topBarPlugin, fileLoaderPlugin, classStylesPlugin, sidebarPlugin, cinematicPlugin, oitPlugin, viewModesPlugin, imagingPlugin, sectionPlugin, pointerModePlugin, gizmoPlugin, cleanupPlugin, classifyPlugin, hoverInfoPlugin, presetsPlugin, penetrationsPlugin, measurePlugin, bcfPlugin, markupPlugin, pointcloudPlugin, xrPlugin, toolbarPlugin, keymapPlugin, exportParamsPlugin, viewsPlugin, issuesPlugin, sheetsPlugin, helpPlugin, panelDockPlugin, awesomeBarPlugin, bootPlugin, undoPlugin];
