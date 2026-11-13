# Settings reference

This file is generated from `web/src/ui/helpText.ts` by `npm run docs`. Do not edit it by hand.
The same texts appear as hover tooltips in the viewer: hover over a setting for 350 ms, or focus a slider with the keyboard.

Each setting has four texts. **Impact** is the plain-language effect: what you see or feel change in the viewer when you move or use the control, in everyday words and without the jargon of the report. The other columns are the technical wording. **Intent** says what the setting does, **Use** says how and when to change it, and **Ref** names the section of the report. The tooltip shows the lines in this order: Intent, Impact, Use, Ref.

Switch the tooltips off with `window.__xrayHelp.disable()` or `localStorage["xray.help"] = "off"`.

## Contents

- [Glossary](#glossary)
- [X-ray](#x-ray)
- [Classification (Alg 1)](#classification-alg-1)
- [Sightlines (Alg 2)](#sightlines-alg-2)
- [Display](#display)
- [Overrides (Alg 7)](#overrides-alg-7)
- [Open model](#open-model)
- [Sample Projects](#sample-projects)
- [Class styles](#class-styles)
- [Classes](#classes)
- [Class styles/*](#class-styles)
- [Cinematic](#cinematic)
- [Camera fly-to](#camera-fly-to)
- [Scene dressing](#scene-dressing)
- [Focus bloom](#focus-bloom)
- [Edge glow](#edge-glow)
- [Sweep reveal](#sweep-reveal)
- [Depth-graded ghosting](#depth-graded-ghosting)
- [Sightlines](#sightlines)
- [AO + vignette (extra GPU cost)](#ao-vignette-extra-gpu-cost)
- [Exploded view (picking stays unexploded)](#exploded-view-picking-stays-unexploded)
- [Fly-through](#fly-through)
- [Turntable](#turntable)
- [Dolly along run](#dolly-along-run)
- [Tour](#tour)
- [Rendering](#rendering)
- [Export / import](#export-import)
- [Panel dock](#panel-dock)
- [Sidebar](#sidebar)
- [View modes](#view-modes)
- [Behind only](#behind-only)
- [Peelback](#peelback)
- [Model cleanup](#model-cleanup)
- [Floating](#floating)
- [Tiny](#tiny)
- [Distant strays](#distant-strays)
- [Duplicates](#duplicates)
- [Degenerate](#degenerate)
- [Model cleanup/Classes](#model-cleanupclasses)
- [Hover info](#hover-info)
- [Presets](#presets)
- [Top bar](#top-bar)
- [Penetrations](#penetrations)
- [Measure](#measure)
- [Clearance](#clearance)
- [BCF](#bcf)
- [Markup](#markup)
- [Sidebar/Issues tab](#sidebarissues-tab)
- [Issues panel](#issues-panel)
- [Issues panel/Segments](#issues-panelsegments)
- [Issues panel/Phone sheet](#issues-panelphone-sheet)
- [Drawing toolbar](#drawing-toolbar)
- [Sheet view](#sheet-view)
- [Sheet view/Back to model](#sheet-viewback-to-model)
- [Sheet view/Fit](#sheet-viewfit)
- [Sheet view/Sketch](#sheet-viewsketch)
- [Sheet view/Draw](#sheet-viewdraw)
- [Sheet view/Drawing toolbar](#sheet-viewdrawing-toolbar)
- [Sheet view/Place in model](#sheet-viewplace-in-model)
- [Sheet view/Model overlay](#sheet-viewmodel-overlay)
- [Sheet view/Overlay opacity](#sheet-viewoverlay-opacity)
- [Place in model](#place-in-model)
- [Sheets/3D opacity](#sheets3d-opacity)
- [Issues panel/View switch](#issues-panelview-switch)
- [Drawing toolbar/View switch](#drawing-toolbarview-switch)
- [Status bar/Open issues](#status-baropen-issues)
- [Markup drawer](#markup-drawer)
- [Keyboard](#keyboard)
- [Imaging](#imaging)
- [MRI slice](#mri-slice)
- [Section](#section)
- [Gizmo](#gizmo)
- [Point cloud](#point-cloud)
- [WebXR](#webxr)
- [Tool strip](#tool-strip)
- [Tool drawer](#tool-drawer)
- [BCF topic dialog](#bcf-topic-dialog)
- [Command palette](#command-palette)
- [Shortcut sheet](#shortcut-sheet)
- [Shortcut editor](#shortcut-editor)
- [Presets drawer](#presets-drawer)
- [View modes drawer](#view-modes-drawer)
- [Measure drawer](#measure-drawer)
- [BCF drawer](#bcf-drawer)
- [Clearance drawer](#clearance-drawer)
- [Penetrations drawer](#penetrations-drawer)
- [Large model drawer](#large-model-drawer)
- [Cleanup drawer](#cleanup-drawer)
- [Imaging drawer](#imaging-drawer)
- [Section drawer](#section-drawer)
- [Scan drawer](#scan-drawer)
- [WebXR drawer](#webxr-drawer)
- [Classify drawer](#classify-drawer)
- [Search bar](#search-bar)
- [Status ba](#status-ba)
- [Status bar](#status-bar)

## Glossary

The texts use these terms with one meaning each.

| Term | Meaning |
| --- | --- |
| alpha | The opacity of an object. The value 1 is solid and the value 0 is invisible. |
| occluder | A context object that is host or near. Only occluders change alpha. |
| sightline | A straight line from a sample point on a focus object to the camera. |
| focus | The objects of interest, such as the selected duct run. The viewer draws focus objects solid and in front. |
| context | The objects that can ghost, such as slabs, walls, beams and columns on nearby storeys. |
| host | A context object that intersects or contains a focus object. |
| near | A context object that is inside the buffer of a focus object and is not a host. |
| far | A context object that is neither host nor near. The report never ghosts a far object. |
| buffer | The distance around a focus object inside which a context object counts as near. |
| ghost | To draw an object with an alpha below 1, so that the focus shows through it. A ghost is an object drawn this way. |
| edge pass | A drawing step that adds outlines at the sharp edges of objects. |
| bloom | A soft glow around the bright parts of the image. The viewer applies it to the focus only. |
| depth of field | A blur of the image parts that are far from the focal distance of the camera. |
| order-independent transparency | A method that blends transparent surfaces without sorting them. The viewer uses weighted blended transparency. |
| storey | A level of the building. An object belongs to at most 1 storey. |
| tier | The rank of an object category. An object of a higher tier ghosts the objects of a lower tier. |
| pin | A rule that keeps the alpha of an object at or above a floor. |
| floor | The lowest alpha that an object may have. A pin, a class style or a hide sets it. |
| explode | To move objects apart, so that objects behind others become visible. |
| sweep | A plane that moves from the camera side through the occluders and reveals the focus behind them. |
| keyframe | A saved camera pose together with the selection and the effect switches. A fly-through connects keyframes. |
| bucket | The result class of an object after classification. The buckets are focus, host, near and far. |
| class | The IFC type of an object, such as IfcSlab or IfcDuctSegment. |
| sample | A point on the surface of a focus object. Each sample casts 1 ray to the camera. |
| layer | The position of an occluder along a ray. Layer 0 is the occluder nearest the camera. |
| occlusion | The fraction of the rays that an occluder blocks. The value is between 0 and 1. |
| importance | The product of occlusion, raised to gamma, and the proximity weight. It sets how far the alpha falls. |
| proximity weight | A number from 0 to 1 that falls with the distance of a near object from the focus. A host has weight 1. |
| ambient occlusion | A shading effect that darkens creases and contact areas. |
| vignette | A darkening of the image towards its corners. |
| motion blur | A blend of successive frames that smears fast camera moves. |
| fly-through | A camera move along a smooth path through the keyframes. |
| turntable | A slow orbit of the camera around the model. |
| dolly | A camera move along the run of the focus objects. |
| peel | A cut that removes the context in front of the focus inside a window. The window follows the outline of the focus. |
| cap | A flat hatched face that closes the cut of a solid, so that the cut shows as a section. |
| section box | A box that clips the model per pixel on all 6 sides. Only the content inside the box stays visible. |
| section plane | A single plane that clips the model per pixel on 1 side. |
| penetration | A place where an MEP element passes through a structural host such as a slab or a wall. |
| clearance | The shortest distance between the surface of a context element and the focus. |
| deviation | The distance from a point of a point cloud to the nearest model surface. |
| preset | A named set of viewer settings. A preset changes many settings in 1 step and never changes the model. |
| palette | A named set of colours for an imaging style. It sets the ground, the tone of the material and the glow. |
| radiograph | An imaging style that draws the context by accumulated material thickness through an attenuation curve. The focus is bright and glows. |
| slab slice | A thin slab through the focus in the MRI style. The slab draws grey and crisp and the surroundings draw faint. |
| viewpoint | A saved camera pose with selected, hidden and coloured elements and clip planes. A BCF topic stores it. |

## Writing rules

Intent and Use follow ASD-STE100 Simplified Technical English, extended with the glossary above.

- One instruction per sentence. At most 20 words per sentence.
- Active voice and present tense. The Use line is in the imperative mood.
- No sentence starts with a gerund. No parentheses, no "e.g." and no "etc.".
- Numbers as digits. A unit follows the number after a space.
- The Ref line starts with `Report:` and names the section and, where it exists, the algorithm line.

Impact follows the same sentence rules and adds these:

- Everyday words at a grade 6 to 8 reading level. It says what you see or feel change on screen.
- A slider: what happens at each end. A switch: what happens on and off. A list: what each choice looks like.
- It uses none of the glossary terms, none of the words of the setting name or folder title, and none of the technical words that the test lists.

## X-ray

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: X-ray* | The panel holds every setting of the X-ray viewer. Each folder groups the settings of a stage. | This panel changes how the building looks on screen. Open a folder to find the controls for one part of the picture. | Open a folder to see its settings. Hover over a setting for 350 ms to read its help. | Report: Purpose |
| X-ray (X) | The switch turns the X-ray mode on or off. In the off state every object keeps alpha 1. | Turn it on and walls and slabs in the way fade so you can see inside. Turn it off and everything looks solid. | Turn the switch off to compare with the plain model. Press the X key for the same action. | Report: Purpose |
| Tiers mode | The switch ranks the object categories in tiers. A tier ghosts only the objects of a lower tier that block it. | On: slabs and walls fade the most, beams and columns fade less, and the selected item stays solid. Off: every blocking part follows one fade rule. | Turn the switch on when several kinds of object compete for the view. Turn it off for a plain focus and context view. | Report: Appendix D, Algorithms 8 and 9 |
| Pin selected | The button pins the selected objects. A pinned object keeps its alpha at or above the user pin floor. | The items you picked stay fairly solid, even behind walls and slabs. Other parts keep fading as before. | Select the objects first. Click the button to keep them clear behind ghosts. | Report: Appendix C, pin sources |
| Hide selected | The button hides the selected objects. A hidden object is not drawn and does not block any sightline. | The items you picked vanish from the picture, and they no longer block the view of what lies behind. | Select the objects that are in the way. Click the button to remove them from the view. | Report: Appendix C, Algorithm 7 |
| Clear pins/hides | The button removes all user pins and all user hides. The class styles stay in force. | Parts you protected or removed come back to normal. The picture returns to the automatic look. | Click the button to return to the automatic result. | Report: Appendix C, pin sources |
| Frame all (F) | The button moves the camera so that the whole model is in view. | The picture zooms and turns until the whole building fits on screen. | Click the button when you lose the model. Press the F key for the same action. | Report: Onboarding checklist |
| Render style | The list sets the look of the X-ray view. The value standard uses ghosts. The values radiograph and mri use the imaging frame. | The first choice shows the building with see-through walls. One choice shows a medical picture of dense parts. The last shows a thin grey slice. | Select radiograph to see the model like a medical image. The imaging controls open below the list. Dimmed settings do not apply. | Report: Appendix G, Imaging and sectioning |

## Classification (Alg 1)

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Classification (Alg 1)* | The folder holds the settings of the static classification. The classification sorts each context object into host, near or far. | These controls pick which walls and slabs fade around the selected item. Change one and the faded group grows or shrinks. | Change a value here to move objects between the buckets. The camera does not affect these settings. | Report: Algorithm 1, lines 1 to 11 |
| bufferBase (m) | The slider sets the base buffer in metres. A context object inside the buffer of a focus object is near. | Move the slider right and more walls and slabs close to the selected item start to fade. Move it left and fewer fade. | Increase the value to make more objects near. Decrease the value to keep the ghosting close to the focus. | Report: Algorithm 1, line 4 |
| bufferScale | The slider sets how much the buffer grows with the cross section of a focus object. The buffer equals the base plus the scale times the cross section. | Move the slider right and thick pipes and ducts pull more walls and slabs into the fade zone. At 0 every item reaches the same distance. | Increase the value to give thick ducts a wider buffer. Set the value to 0 to use the base buffer for all objects. | Report: Algorithm 1, line 4 |
| bufferLo (m) | The slider sets the smallest buffer in metres. The buffer never falls below this value. | Move the slider right and even thin pipes make walls and slabs close to them fade. Move it left and thin pipes affect fewer parts. | Increase the value to stop thin pipes from getting a tiny buffer. Keep the value below the high limit. | Report: Parameters and defaults |
| bufferHi (m) | The slider sets the largest buffer in metres. The buffer never rises above this value. | Move the slider left and big ducts affect fewer walls and slabs. Move it right and they reach out to more of the building. | Decrease the value to stop large ducts from ghosting distant structure. Increase the value to include more structure around large ducts. | Report: Parameters and defaults |
| storeyBand | The slider sets how many storeys above and below the focus storey count as context. Objects on other storeys are not context. | At 0 only walls and slabs on the same level as the selected item can fade. Higher values add levels above and below. | Set the value to 0 to use the storey of the focus only. Increase the value to include the storeys above and below. | Report: Algorithm 1, line 2 |

## Sightlines (Alg 2)

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sightlines (Alg 2)* | The folder holds the settings of the sightline test. The test runs after each camera move and sets the target alpha of each occluder. | These controls set how much the walls and slabs in the way fade out. They also set how fast the fade happens. | Change a value here to make the ghosting stronger, weaker or faster. | Report: Algorithm 2, lines 1 to 12 |
| samplesPerObject | The slider sets how many sample points the test takes on each focus object. Each sample casts 1 ray to the camera. | Move the slider right and the fade looks steadier but updates more slowly. Move it left and it updates faster but can flicker. | Increase the value to get a smoother occlusion result. Decrease the value to run the test faster. | Report: Algorithm 2, line 1 |
| maxSamples | The slider sets the upper limit of sample points for all focus objects together. The limit keeps the test fast for a large focus. | Move the slider left and big selections update faster, but the fade may flicker. Move it right and the fade stays steady. | Decrease the value if the frame rate falls during orbit. Increase the value if the ghosting flickers on a large run. | Report: Algorithm 2, line 1 |
| alphaMin | The slider sets the lowest alpha that an occluder reaches. An occluder with full importance gets this alpha. | Move the slider left and the walls and slabs in the way fade almost to nothing. Move it right and they stay more solid. | Decrease the value to make blocking objects more transparent. Increase the value to keep them more solid. | Report: Algorithm 2, line 9 |
| alphaMax | The slider sets the highest alpha of an occluder. An occluder that blocks nothing gets this alpha. | Move the slider right and parts that block nothing look fully solid. Move it left and they look slightly faded. | Increase the value to keep the context solid when it does not block. Decrease the value to ghost all occluders a little. | Report: Algorithm 2, line 9 |
| gamma | The slider sets the exponent that shapes importance from occlusion. Importance equals occlusion to the power gamma times the proximity weight. | Move the slider left and a part that blocks only a little still fades a lot. Move it right and only big blockers fade. | Decrease the value below 1 to ghost an occluder that blocks only a few rays. Increase the value above 1 to ghost only strong blockers. | Report: Algorithm 2, line 8 |
| occluder scope | The list sets which context objects take part in the ray test. The value near tests host and near objects. The value all tests far objects too. | Choose all and a distant wall that blocks the view fades too. The other choice fades only parts close to the selected item. | Select near to follow the report. Select all to ghost a far object that blocks the view. | Report: Limitations and extensions, Far occluders note |
| far weight | The slider sets the proximity weight of a far occluder when the scope is all. A far object has no proximity weight of its own. | Move the slider right and distant walls that block the view fade more. At 0 they stay fully solid. It works only when the list above says all. | Increase the value to ghost far blockers more. Set the value to 0 to keep far objects solid. | Report: Limitations and extensions, Far occluders note |
| smoothingRate | The slider sets the fraction of the alpha change that the viewer applies on each step. The value 1 turns the smoothing off. | Move the slider left and walls and slabs fade slowly and calmly. Move it right and they follow the camera at once. | Decrease the value to make alpha changes slow and calm. Increase the value to make the ghosts follow the camera at once. | Report: Algorithm 2, line 11 |
| layer weighting | The list sets how stacked occluders on a ray share the credit. Front gives the occluder nearest the camera the most transparency, with a falloff per layer. | Choose front and the slab closest to the camera fades most while slabs below it stay firmer. Choose budget and only the top few slabs fade. Choose uniform and every slab in a stack fades the same. | Select front to see through a stack of slabs from the nearest slab. Select budget to ghost only the first layers. Select uniform to give all layers equal credit. | Report: Algorithm 2, lines 2 to 5 |
| layer falloff | The slider sets the credit factor for each layer behind the nearest layer. It acts under front weighting. The value 0.5 gives credits 1, 0.5 and 0.25. | Move the slider left and only the top slab of a stack fades while lower slabs stay firm. Move it right and lower slabs fade almost as much. It works only when the list above says front. | Decrease the value to ghost mainly the nearest layer. Increase the value to ghost deeper layers almost as much. | Report: Algorithm 2, lines 2 to 5 |
| layer budget | The slider sets how many layers per ray ghost under budget weighting. Deeper layers get no credit. | Set it to 1 and only the top slab of a stack fades. Move it right and more slabs below fade too. It does nothing while the list two rows up says front or uniform. | Set the value to 1 to ghost only the nearest layer. Increase the value to open the view through more layers. | Report: Algorithm 2, lines 2 to 5 |

## Display

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Display* | The folder holds the settings that only change how the viewer draws. They do not change the classification. | These controls change the outlines and colours of faded parts. They also decide whether distant parts stay in the picture. | Change a value here to adjust outlines, ghost colour and the far objects. | Report: Rendering in Bonsai/Blender |
| edgeAlpha | The slider sets the alpha of the outlines drawn by the edge pass. An outline is never fainter than its object. | Move the slider right and the outlines of faded walls and slabs get darker and easier to see. At 0 they fade along with their parts. | Increase the value to see the outlines of ghosts clearly. Set the value to 0 to remove the outlines of ghosts. | Report: Appendix B, WebGL |
| ghost desaturate | The slider sets how much colour a ghost loses. The value 1 draws ghosts in grey. | Move the slider right and faded parts turn grey, so the selected item stands out. Move it left and they keep their own colours. | Increase the value to separate the ghosts from the focus by colour. Decrease the value to keep the material colours. | Report: Rendering in Bonsai/Blender |
| focus in front | The switch draws the focus objects on top of all other objects. The focus then stays visible behind solid structure. | Turn it on and the selected item always shows, even behind a solid wall. Turn it off and solid walls can hide it. | Turn the switch on to see the focus through any wall. Turn it off to let solid objects hide the focus. | Report: Appendix B, WebGL |
| far mode | The list sets how the far objects draw. The value opaque draws them normally. The value hidden removes them. | Choose opaque and distant walls and slabs stay in the picture. Choose hidden and they disappear. | Select hidden to see only the focus and its occluders. Select opaque to see the full model. | Report: Algorithm 1, line 5 |
| debug colour by bucket | The switch paints each object with the colour of its bucket. Focus, host, near and far each have 1 colour. | On: parts that the selected item crosses turn red, close ones turn orange and distant ones turn grey. Off: normal materials return. | Turn the switch on to check the classification. Turn it off before you judge the final look. | Report: Terminology |

## Overrides (Alg 7)

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Overrides (Alg 7)* | The folder holds the settings of the opacity floors. A floor stops an object from ghosting below a given alpha. | This folder sets how strongly protected parts resist fading. A higher value keeps them easier to see. | Change the pin floor here. Use the buttons of the X-ray folder to pin or hide objects. | Report: Appendix C, Algorithm 7 |
| user pin floor | The slider sets the lowest alpha of a pinned object. A pinned object never ghosts below this value. | Move the slider right and protected parts stay more solid behind walls. At 0 they can fade out completely. | Increase the value to keep pinned objects clearer. Set the value to 0 to let pinned objects fade fully. | Report: Appendix C, pin sources |

## Open model

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Open model* | The folder holds the controls that open a model file from your own computer. The viewer reads the file in the browser. No data leaves your computer. | These controls let you look at your own building file. Your file stays on your computer and goes nowhere else. | Click Open IFC or glb file to choose a file. Drop files on the viewer for the same action. | Report: Appendix B, WebGL |
| Open IFC or glb file | The button opens a file picker for your own model files. The viewer reads the files in the browser and sends nothing out. You can also drop files on the viewer. | Click and a window lets you pick a building from your computer. You can also drag it onto the picture. | Click the button. Choose a model file from your computer. Read the status line for the result. | Report: Appendix B, WebGL |
| Cancel load | The button stops a load in progress. The viewer keeps the current model. | Click while a new building is coming in and it stops. The building you see now stays on screen. | Click the button when a load takes too long or you chose the wrong file. | Report: Appendix B, WebGL |
| Load status | The field shows the progress of a load, then the result or an error. You cannot edit it. | The text shows progress while a building comes in. It then says whether it worked or what went wrong. | Read the field after you choose a file. Read the error text if the model does not appear. | Report: Appendix B, WebGL |
| edges | The list sets whether the loader builds edge lines for an IFC file. The value auto skips edge lines above 50,000 elements. | Choose none, or auto on a big building, and the file loads faster. The sharp outlines then go missing. Choose all to keep every outline. | Select auto for most files. Select none for a huge file. Select all to force edge lines. The choice applies to the next IFC file that you open. | Report: Appendix K, Packaging, point clouds and large models |
| properties | The list sets whether the loader reads the properties of each element from an IFC file. The value none skips property extraction for speed. | Choose none and a big file loads faster. The info card and the side list then have no facts to show. Choose common to keep them. | Select common to keep the usual facts. Select none for the fastest load. The choice applies to the next IFC file that you open. | Report: Appendix L, Hover info and properties |
| Model stats | The read-only field shows the size of the last model. It lists the elements, the triangles and the load time. | A short text of numbers tells you how big the building is and how long it took to load. | Read the line after a load. Open the Large model tool for all figures. | Report: Appendix K, Packaging, point clouds and large models |

## Sample Projects

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sample Projects* | The folder lists the example models that come with the viewer. Each example has a readable name. | Each chosen entry replaces the scene on screen. Saved views and share links still open the model they name. | Open the Model list in the folder. Choose an entry and wait until the loading message disappears. | Report: Onboarding checklist |
| Model | The list selects the example model to load. Models that you opened from files are listed after the examples. | The viewer replaces the current scene with the chosen one. An entry marked as needing the served app or the zip stays out of this file. | Select a model name from the list. Wait until the loading message disappears. | Report: Onboarding checklist |

## Class styles

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Class styles* | The folder holds the styles of the object classes. A style sets alpha limits, a floor, a hide flag and a colour for a class. | This folder lets you set the look of each kind of building part, such as walls or slabs. Changes show at once. | Open the Classes folder to edit a class. Use the buttons to reset, export or import all styles. | Report: Appendix C, pin sources |
| Reset to config | The button discards your edits of the class styles. The styles return to the config file and the model sidecar. | Click and every change you made to the look of parts vanishes. Each kind of part returns to the look its files give it. | Click the button to undo all class edits at once. | Report: Appendix C, pin sources |
| Export JSON | The button saves the effective class styles as the file xray.config.json. | Click and your browser saves a small file with the looks you set for each kind of part. You can send the file to other people. | Click the button to share the styles with a colleague. Put the file in the public folder to make it the default. | Report: Onboarding checklist |
| Import JSON | The button loads class styles from a JSON file. The loaded styles replace your earlier edits. | Click, pick a look file, and the parts change to match it. Your earlier changes are gone. | Click the button. Select a file. Check the result in the Classes folder. | Report: Onboarding checklist |

## Classes

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Classes* | The folder lists 1 sub folder for each class in the model. The number after a class name is its object count. | This folder lists every kind of building part in the model. Open one to restyle all parts of that kind. | Open the sub folder of a class to change its style. | Report: Appendix C, pin sources |

## Class styles/*

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Class styles/** | The folder sets the style of the class *class*. The style applies to every object of that class. | Every part of the kind *class* changes together. Open the folder to change how they fade, show or look. | Open the folder to change the class. Click Reset this class to remove your edits. | Report: Appendix D, category priority |
| alpha max | The slider sets the highest alpha of objects of the class *class*. These objects never draw above this alpha. | Move the slider left and every part of this kind looks a little faded, even when nothing blocks the view. At 1 they look normal. | Decrease the value to keep the class a little transparent at all times. Set the value to 1 for the normal look. | Report: Appendix D, category priority |
| alpha min | The slider sets the lowest alpha that the sightline test gives to objects of the class *class*. | Move the slider right and parts of this kind fade less when they block the view. Move it left and they can fade almost away. | Increase the value to protect the class from strong ghosting. Decrease the value to let the class fade more. | Report: Algorithm 2, line 9 |
| floor | The slider sets the floor of objects of the class *class*. The alpha of these objects never falls below the floor. | Move the slider right and parts of this kind stay more solid, even when they block the view. At 0 they can fade away fully. | Increase the value to keep the class visible. Set the value to 0 to remove the floor. | Report: Appendix C, pin sources |
| hidden | The switch hides all objects of the class *class*. Hidden objects are not drawn and do not block sightlines. | Turn it on and every part of this kind disappears from the picture. The things behind them show clearly. | Turn the switch on to remove a class that is in the way. | Report: Appendix C, Algorithm 7 |
| color | The colour box sets the base colour of objects of the class *class*. | Pick a shade and every part of this kind takes that shade at once. | Click the box. Pick a strong colour to find a class quickly. | Report: Rendering in Bonsai/Blender |
| Reset this class | The button removes all your edits of the class *class*. The class returns to the config and sidecar values. | Click and the changes you made to that kind of part vanish. Its sliders return to their start values. | Click the button to undo the changes of this class only. | Report: Appendix C, pin sources |

## Cinematic

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Cinematic* | The folder holds optional visual effects and camera moves. The effects do not change the classification or the alpha of any object. | This folder adds film-style looks and camera moves. None of them change which parts fade. | Open a sub folder to change an effect. Turn effects off to gain frame rate. | Report: Limitations and extensions |

## Camera fly-to

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Camera fly-to* | The folder controls the camera move that follows a new selection. | These controls decide whether the view glides toward each item you select. When off, the view stays where it is. | Turn the move on to keep the focus in view. Turn it off to move the camera by hand. | Report: Limitations and extensions |
| Fly to selection | The switch moves the camera to the focus when you select an object. The move is smooth. | On: the view glides toward each new item you pick. Off: the view stays where it is. | Turn the switch on to keep the selection in view. Turn it off to keep the camera where it is. | Report: Limitations and extensions |
| Duration (ms) | The slider sets the time of a camera fly-to in milliseconds. | Move the slider right and the glide to a new item takes longer and looks calmer. Move it left and it feels quick. | Increase the value for a slow and calm move. Decrease the value for a fast move. | Report: Limitations and extensions |
| Fly to focus now | The button moves the camera to the focus objects at once. | Click and the view glides back to the selected item. Use it after you drift away. | Click the button after you orbit away from the focus. | Report: Limitations and extensions |
| Staggered reveal | The switch delays the fade of each occluder by its distance from the focus. The transparency spreads outward from the focus. | On: walls and slabs fade one after another, spreading outward from the selected item. Off: they all fade together. | Turn the switch on to show the ghosting as a ripple. Turn it off to ghost all occluders at the same time. | Report: Limitations and extensions |

## Scene dressing

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Scene dressing* | The folder controls the sky, the fog, the lights and the ground shadow. They improve the look and do not change the result. | These controls add a sky colour, haze and soft shading to the picture. Turn them off for plain flat colours. | Turn the dressing off to see plain colours. Reduce the fog if distant objects look washed out. | Report: Limitations and extensions |
| Sky, fog, lights | The switch adds a gradient sky, distance fog and a key and fill light. | On: a soft backdrop, thin haze and gentle shading appear. Off: the background turns plain and the shading goes flat. | Turn the switch on for a pleasant still image. Turn it off to see the plain colours. | Report: Limitations and extensions |
| Fog strength | The slider sets how strongly distance fog fades far objects into the sky. | Move the slider right and distant parts melt into a pale haze. Move it left and every part keeps its full colour. | Increase the value to push distant structure back. Decrease the value if the model looks washed out. | Report: Limitations and extensions |
| Ground shadow plane (+1 draw) | The switch adds a soft shadow plane under the model. It costs 1 extra draw call. | On: a soft dark patch appears under the building, so it looks like it rests on something. Off: it looks like it floats. | Turn the switch on to anchor the model to the ground. Turn it off to save a draw call. | Report: Appendix B, WebGL |
| Shadow strength | The slider sets the darkness of the ground shadow. | Move the slider right and the dark patch under the building gets darker. Move it left and it almost vanishes. | Increase the value for a clear shadow. Decrease the value for a faint shadow. | Report: Limitations and extensions |

## Focus bloom

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Focus bloom* | The folder controls the glow around the focus objects. Context objects never glow. | These controls add a soft glow around the item you picked. Walls and slabs never glow. | Turn the bloom on to find the focus quickly in a busy model. | Report: Limitations and extensions |
| Selective bloom | The switch adds a bloom around the focus objects only. Context objects do not glow. | On: a soft glow surrounds the item you picked, so it jumps out of a busy picture. Off: it looks plain. | Turn the switch on to find the focus in a busy view. | Report: Limitations and extensions |
| Strength | The slider sets the brightness of the bloom. | Move the slider right and the glow around the selected item gets brighter. Very high values wash out its colour. | Increase the value for a strong glow. Decrease the value if the focus colour washes out. | Report: Limitations and extensions |
| Radius | The slider sets how far the bloom spreads. | Move the slider right and the glow spreads wider and softer. Move it left and it hugs the item tightly. | Increase the value for a wide, soft glow. Decrease the value for a tight glow. | Report: Limitations and extensions |

## Edge glow

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Edge glow* | The folder controls a glowing outline. The glow scope sets which objects get the outline. | These controls draw a bright line around the item you picked, and on request around the parts close to it. | Turn the glow on. Select focus for the selection only. Select near or all for more objects. | Report: Terminology, focus |
| Edge glow | The switch adds a glowing outline to the objects of the glow scope. The default scope is the focus. | On: a bright line shows around the item you picked. Off: it looks normal. | Turn the switch on to find the selection quickly in a busy model. | Report: Terminology, focus |
| glow scope | The list sets which objects glow. The value focus glows the focus. The value near adds the host and near objects. The value all glows every visible object. | Choose the first and only the item you picked gets a bright line. The middle choice adds the walls and slabs close to it. The last choice lines every part. | Select focus for a clear view. Select near to see the penetrations. Select all for a line drawing of the model. | Report: Terminology, host |
| Additive | The switch adds the glow colour to the image instead of replacing the colour below. | On: the line adds light to what lies behind it, so it shines on dark parts. Off: it looks flat and solid. | Turn the switch on for a bright glow on dark ghosts. Turn it off for a flat outline. | Report: Appendix B, WebGL |
| Strength | The slider sets the brightness of the edge glow. | Move the slider right and the bright line gets bolder and brighter. Move it left and it almost disappears. | Increase the value to make the outline stand out. Decrease the value for a quiet outline. | Report: Limitations and extensions |
| Colour | The colour box sets the colour of the edge glow. | Pick a shade for the bright line. A shade unlike the selected item makes it stand out. | Click the box. Pick a colour that differs from the focus colour. | Report: Limitations and extensions |

## Sweep reveal

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sweep reveal* | The folder controls the reveal in which a sweep plane moves from the camera through the occluders. | These controls shape the quick wipe that opens a clear view when walls and slabs fade. | Turn the reveal on to show the focus with a clear start. Turn it off to ghost at once. | Report: Limitations and extensions |
| Sweep reveal | The switch starts a sweep when the ghosting changes. The sweep moves from the camera through the occluders. | On: when walls and slabs fade, a bright stripe wipes from the camera toward the selected item. Off: they fade at once. | Turn the switch on to show the focus with a clear start. Turn it off to ghost at once. | Report: Limitations and extensions |
| Mode | The list selects the reveal style. The value stagger delays each occluder. The value sweep moves a plane. The value both uses sweep and stagger. | Stagger makes parts fade one by one, spreading outward. The second choice wipes a bright stripe across the picture. Both does the two together. | Select sweep for a clean plane. Select stagger for a ripple from the focus. Select both for the full effect. | Report: Limitations and extensions |
| Duration (ms) | The slider sets the time of the sweep in milliseconds. | Move the slider right and the wipe takes longer and looks slower. Move it left and it ends in a blink. | Increase the value for a slow reveal. Decrease the value for a quick reveal. | Report: Limitations and extensions |
| Band width (m) | The slider sets the width of the bright band at the sweep plane in metres. | Move the slider right and the bright stripe gets thicker and easier to spot. Move it left and it shrinks to a thin line. | Increase the value for a wide band that is easy to see. Decrease the value for a thin line. | Report: Limitations and extensions |

## Depth-graded ghosting

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Depth-graded ghosting* | The folder controls the tint of the ghosts by depth. A ghost far in front of the focus looks cooler and darker. | These controls tint faded parts darker and bluer when they lie well in front of the selected item. | Turn the grading on to read the depth order of the ghosts. | Report: Limitations and extensions |
| Depth grading | The switch tints the ghosts by their depth in front of the focus. Far ghosts look cooler and darker. | On: faded parts that sit well in front of the selected item look darker and bluer. Off: all faded parts share one tint. | Turn the switch on to read the depth order of the ghosts. | Report: Limitations and extensions |
| Strength | The slider sets the largest mix of the cool dark tone into a ghost. | Move the slider right and the dark blue tint on faded parts gets heavier. Move it left and the tint is hard to see. | Increase the value to grade the depth strongly. Decrease the value for a subtle grade. | Report: Limitations and extensions |

## Sightlines

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sightlines* | The folder controls the drawing of the sightlines of the focus. The viewer draws them for a short time and fades them out. | These controls draw thin lines from the selected item to the camera for a moment. The lines show what blocks the view. | Click Show sightlines to check which rays an occluder blocks. | Report: Algorithm 2, lines 2 to 5 |
| Show sightlines | The button draws the sample rays from the focus to the camera for a short time. | Click and thin lines run from the selected item to the camera, then vanish. Orange lines hit something and blue lines have a free view. | Click the button to see which occluders block the focus. Orbit first to choose the view. | Report: Algorithm 2, lines 2 to 5 |
| On selection | The switch draws the sightlines each time you select an object. | On: the thin lines appear each time you pick an item. Off: they appear only when you click the button. | Turn the switch on to inspect every selection. Turn it off for a clean view. | Report: Algorithm 2, lines 2 to 5 |
| Style | The list selects how the rays draw. The value lines draws segments. The value dots draws hit points. The value both draws lines and dots. | Choose lines for long thin strokes. Choose dots for small spots where each line meets a wall or slab. Choose both to see the two together. | Select lines to follow the paths. Select dots to see where the rays hit. | Report: Algorithm 2, lines 2 to 5 |
| Which rays | The list selects which rays draw. The value blocked draws rays that hit an occluder. The value unblocked draws the free rays. | Choose blocked to see only the lines that hit a wall or slab. Choose unblocked to see the lines with a free view. Choose all to see both. | Select blocked to find the cause of ghosting. Select unblocked to see the free view. | Report: Algorithm 2, line 7 |
| Colour by hit | The switch colours each ray by its result. Blocked rays and free rays get different colours. | On: lines that touch a wall or slab turn orange and free lines turn blue. Off: every line looks the same pale shade. | Turn the switch on to separate blocked rays from free rays at a glance. | Report: Algorithm 2, line 7 |
| Max rays | The slider sets the largest number of rays to draw. | Move the slider right and more lines show, so the picture gets busier. Move it left and only a few lines show. | Decrease the value to keep the picture clear. Increase the value to show more samples. | Report: Algorithm 2, line 1 |
| Fade (s) | The slider sets the time in seconds before the drawn rays fade out. | Move the slider right and the lines stay on screen longer. Move it left and they vanish quickly. | Increase the value to study the rays longer. Decrease the value to clear the view sooner. | Report: Limitations and extensions |

## AO + vignette (extra GPU cost)

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: AO + vignette (extra GPU cost)* | The folder controls ambient occlusion and the vignette. Both effects cost GPU time. | These controls add soft shading in corners and darker picture corners. They look richer but can make the picture update slower. | Turn the effects on for still images. Turn them off for a high frame rate. | Report: Appendix B, WebGL |
| AO (GTAO, half res) | The switch adds ambient occlusion at half resolution. It darkens creases and contact areas. | On: soft dark shading appears in corners and where parts meet, which gives the picture a richer look. Off: surfaces look flat but update faster. | Turn the switch on for still images with more depth. Turn it off for a high frame rate. | Report: Appendix B, WebGL |
| AO radius (m) | The slider sets the reach of the ambient occlusion in metres. | Move the slider right and the dark shading spreads over wider gaps. Move it left and it stays in tight corners. | Increase the value to shade larger gaps. Decrease the value to shade only tight corners. | Report: Appendix B, WebGL |
| AO intensity | The slider sets the strength of the ambient occlusion shading. | Move the slider right and the dark shading in corners gets deeper. Move it left and the shading is hard to notice. | Increase the value for dark creases. Decrease the value for a light touch. | Report: Appendix B, WebGL |
| Vignette | The switch darkens the image towards its corners. | On: the picture corners turn darker, which draws the eye to the middle. Off: the whole picture looks even. | Turn the switch on to draw the eye to the centre. Turn it off for an even image. | Report: Limitations and extensions |
| Vignette darkness | The slider sets how dark the corners become. | Move the slider right and the picture corners get very dark. Move it left and they stay light. | Increase the value for strong corners. Decrease the value for a faint effect. | Report: Limitations and extensions |

## Exploded view (picking stays unexploded)

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Exploded view (picking stays unexploded)* | The folder controls the exploded view. The view moves objects apart so that the focus shows. A click selects objects at their original positions. | These controls pull parts of the building apart. That opens a clear path to the item you want to see. | Click Explode to move the objects. Select the mode and the distances first. | Report: Limitations and extensions |
| Explode | The button moves the objects apart with an animation. The same button moves them back. | Click and parts of the building slide apart, so hidden parts come into sight. Click again and they slide back. | Select an object first. Click the button to open a path to the focus. | Report: Limitations and extensions |
| explode | The list selects which objects move. The value auto picks the selection or its occluders. The value both moves the selection and its occluders. | Choose which parts slide apart. Auto lets the program decide. The other choices move your chosen items, the parts in their way, or both. | Select occluders to clear the view of a single object. Select selection to move the selected group apart. | Report: Limitations and extensions |
| Mode | The list selects the way the objects move. The value radial moves them away from the centre. The value storeys separates the storeys. | Radial pushes parts outward from the middle like a burst. The second choice lifts each level of the building apart. The third does both. | Select radial for a classic exploded view. Select storeys to lift each storey apart. Select radial+storeys for both. | Report: Terminology, storey |
| Radial factor | The slider sets the distance of the radial move as a multiple of the distance from the centre. | Move the slider right and parts slide much further out. Move it left and the picture looks compact. | Increase the value to push the objects far apart. Decrease the value for a compact view. | Report: Limitations and extensions |
| Storey gap (m) | The slider sets the vertical gap in metres between neighbouring storeys. | Move the slider right and the levels of the building lift further apart. Move it left and they sit close together. | Increase the value to see each storey alone. Decrease the value to keep the storeys close. | Report: Terminology, storey |
| Min push (m) | The slider sets the smallest radial move in metres. An object that is near the centre moves at least this far. | Move the slider right and parts that sit very close to the middle still slide out clearly. At 0 they may barely move. | Increase the value to clear objects that sit close to the focus. Set the value to 0 to turn it off. | Report: Limitations and extensions |
| Duration (ms) | The slider sets the time of the explode move in milliseconds. | Move the slider right and the parts take longer to slide apart or back. Move it left and they snap into place. | Increase the value for a slow move. Decrease the value for a fast move. | Report: Limitations and extensions |

## Fly-through

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Fly-through* | The folder controls the fly-through. A fly-through is a smooth camera move through saved keyframes. | These controls build a film-like camera trip from saved views. You can watch it or record a video. | Add 2 or more keyframes. Click Play to run the move and Record to save a video. | Report: Limitations and extensions |
| Keyframes | The field shows how many keyframes the fly-through holds. You cannot edit it. | The number shows how many saved views the trip holds. You need at least 2 to watch it. | Read the count before you play. Add at least 2 keyframes. | Report: Limitations and extensions |
| Add keyframe | The button saves the current camera pose, selection and effect switches as a new keyframe. | Click and the viewer saves the current camera position as one stop on the trip. The count goes up by 1. | Move the camera to a view. Click the button to save it. | Report: Limitations and extensions |
| Remove last | The button deletes the last keyframe. | Click and the final stop on the trip disappears. The count goes down by 1. | Click the button to undo the last keyframe you added. | Report: Limitations and extensions |
| Clear | The button deletes all keyframes. | Click and every stop on the trip disappears, so you can start again. | Click the button to start a new fly-through. | Report: Limitations and extensions |
| Load from selection sets | The button creates 1 keyframe for each saved selection set. Each keyframe frames its set. | Click and the trip gets one stop for each saved group. Each stop looks at its group. | Save selection sets in the sidebar first. Click the button to build a fly-through from them. | Report: Onboarding checklist |
| Seconds per segment | The slider sets the time in seconds between 2 keyframes. | Move the slider right and the trip takes longer between stops, so it feels calm. Move it left and it feels hurried. | Increase the value for a slow move. Decrease the value for a quick reveal. | Report: Limitations and extensions |
| Play / stop | The button starts or stops the fly-through along a smooth path through the keyframes. | Click and the camera glides along the saved views like a film. Click again and the film ends. | Click the button to play. Click it again to stop. | Report: Limitations and extensions |
| Record (webm download) | The button plays the fly-through and records it as a webm video that the browser downloads. | Click and the trip runs on its own while the viewer films it. Your browser then saves the video. | Add the keyframes first. Click the button. Wait until the download starts. | Report: Limitations and extensions |
| Export JSON | The button saves the keyframes as a JSON file. | Click and your browser saves a small file holding your saved views. You can reuse it later or share it. | Click the button to keep a fly-through or to share it. | Report: Onboarding checklist |
| Import JSON | The button loads keyframes from a JSON file. The loaded keyframes replace the current ones. | Click, pick a trip file, and its saved views replace the ones you have now. | Click the button. Select a fly-through file. | Report: Onboarding checklist |
| Depth of field (playback) | The switch adds depth of field during playback. The parts away from the focal distance blur. | On: during the trip the main item stays crisp while the rest of the picture turns soft. Off: everything stays sharp. | Turn the switch on for a film look. Turn it off for a sharp image and a high frame rate. | Report: Appendix B, WebGL |
| Aperture | The slider sets the strength of the depth of field blur. | Move the slider right and more of the picture around the main item turns soft. Move it left and more stays sharp. | Increase the value for a shallow focus. Decrease the value for a deep focus. | Report: Appendix B, WebGL |
| Motion blur (playback) | The slider sets how much of the previous frame mixes into the next frame during playback. Fast camera moves look smooth. | Move the slider right and fast camera moves leave soft trails and look smoother during the trip. At 0 every picture stays crisp. | Increase the value for recorded video. Set the value to 0 to see crisp frames. | Report: Appendix B, WebGL |

## Turntable

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Turntable* | The folder controls the turntable. The camera orbits the model at a constant speed. | These controls spin the picture slowly around the building so you see every side. It pauses while you use the mouse. | Turn the auto-orbit on to show the model from all sides. | Report: Limitations and extensions |
| Auto-orbit | The switch turns the camera around the model at a constant speed. It stops when you touch the view. | On: the picture spins slowly around the building so you see every side. Off: it stays where you leave it. | Turn the switch on to show the model from all sides. | Report: Limitations and extensions |
| Speed (deg/s) | The slider sets the orbit speed in degrees per second. A negative value turns the other way. | Move the slider right and the spin gets faster. Values below zero spin the other way. | Increase the value for a fast orbit. Use a negative value to reverse the direction. | Report: Limitations and extensions |

## Dolly along run

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Dolly along run* | The folder controls the dolly. The camera follows the run of the focus objects. | These controls glide the camera beside the selected pipe or duct, from one end to the other. | Select a duct or pipe run. Click Play dolly to start the move. | Report: Limitations and extensions |
| Play dolly | The button moves the camera along the run of the focus objects. The same button pauses the move. | Click and the camera glides beside the selected pipe or duct, from end to end. Click again and it holds still. | Select a duct or pipe run first. Click the button to start. Click it again to pause. | Report: Limitations and extensions |
| Speed (m/s) | The slider sets the speed of the dolly in metres per second. | Move the slider right and the camera glides faster. Move it left and you have time to study every fitting. | Increase the value for a fast move. Decrease the value to inspect fittings. | Report: Limitations and extensions |
| Height offset (m) | The slider sets the height of the camera above the run in metres. | Move the slider right and the camera rises above the pipe and looks down on it. Below zero it travels under the pipe. | Increase the value to look down on the run. Set the value to 0 to travel at the level of the run. | Report: Limitations and extensions |
| Progress | The slider shows and sets the position of the camera along the run. The value 0 is the start and the value 1 is the end. | The slider shows how much of its path the camera has covered. Drag it to slide the camera back and forth by hand. | Drag the slider to scrub along the run. The drag pauses the dolly. | Report: Limitations and extensions |

## Tour

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Tour* | The folder controls the tour. The tour selects the saved selection sets in turn. | These controls visit your saved groups one by one. The picture glides to each group and stays a few seconds. | Save 2 or more selection sets in the sidebar. Click Play tour to start. | Report: Onboarding checklist |
| Play tour | The button selects the saved selection sets in turn and flies to each. The same button stops the tour. | Click and the picture visits your saved groups one by one, staying a few seconds on each. Click again and it ends. | Save 2 or more selection sets first. Click the button to start. Click it again to stop. | Report: Onboarding checklist |
| Hold (s) | The slider sets the time in seconds that the tour stays on each selection set. | Move the slider right and the picture stays longer on each saved group. Move it left and the visits go quickly. | Increase the value to give viewers time to read the view. Decrease the value for a short tour. | Report: Onboarding checklist |
| Loop | The switch restarts the tour after the last selection set. | On: after the last saved group, the visits start again from the first. Off: they end after the last. | Turn the switch on for a continuous show. Turn it off to stop at the end. | Report: Onboarding checklist |

## Rendering

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Rendering* | The folder holds the settings of the transparency method used for the ghosts. | These controls change how overlapping see-through walls and slabs mix their colours. Cleaner mixing can make the picture slower. | Turn on order-independent transparency if overlapping ghosts show the wrong blend order. | Report: Appendix E, McGuire and Bavoil 2013 |
| order-independent ghosts | The switch draws the ghosts with weighted blended order-independent transparency. The method removes sorting errors where ghosts overlap. | On: overlapping see-through walls and slabs mix cleanly, whichever one is in front. Off: the colours at overlaps may look wrong. | Turn the switch on when overlapping ghosts show a wrong blend order. Turn it off to save GPU time. | Report: Appendix E, McGuire and Bavoil 2013 |
| depth weight | The list sets the blend weight of a ghost fragment. The value paper lets a nearer ghost count more. The value flat uses the alpha only. | Choose paper and the closer see-through part wins more of the colour. Choose flat and distant ones show through more evenly. | Select paper to follow McGuire and Bavoil 2013. Select flat if distant ghosts look too faint. | Report: Appendix E, McGuire and Bavoil 2013 |
| OIT antialiasing | The switch smooths the edges of ghosts that the transparency method draws. It uses 4 samples per pixel. | On: the outlines of see-through parts look smooth instead of jagged. Off: they may show small stair steps but the picture updates faster. | Turn the switch on for clean ghost edges. Turn it off to save GPU memory and time. | Report: Appendix B, WebGL |
| float buffers | The field shows whether the GPU supports the float colour buffers that the transparency method needs. You cannot edit it. | The text tells you whether your graphics card can mix overlapping see-through parts cleanly. If it says no, the first switch in this folder stays unavailable. | Read the field if the order-independent switch is disabled. Use a newer browser or GPU to enable it. | Report: Appendix B, WebGL |

## Export / import

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Export / import* | The folder holds the actions that save, share and restore all settings of the viewer as JSON. | These buttons save your settings to a file or bring them back. They also let you share your view with other people. | Export the settings before an experiment. Import the file later to return to the same state. | Report: Onboarding checklist |
| Export JSON | The button downloads all settings of the viewer as a JSON file. The file holds the classification, the sightlines, the styles and the effects. | Click and your browser saves a small file with all your settings. Keep it to restore this look later. | Click the button to keep a setup or to share it. Name the file after the project. | Report: Onboarding checklist |
| Copy JSON | The button copies all settings of the viewer to the clipboard as JSON text. | Click and your settings go onto the clipboard as text. Paste them into a message or a note. | Click the button. Paste the text into a message or a file. | Report: Onboarding checklist |
| Import JSON | The button loads settings from a JSON file. The viewer applies the values and reports any value it cannot use. | Click, pick a settings file, and the viewer takes on those settings. It tells you about any value it cannot use. | Click the button. Select a file that you exported before. | Report: Onboarding checklist |
| Copy share URL | The button copies a link that carries the main settings and the camera. The link opens the same view. | Click and a web link goes onto the clipboard. A friend who opens it with the same building sees your picture. | Click the button. Send the link to a colleague who uses the same model. | Report: Onboarding checklist |
| Export Python dict | The button downloads the settings as a Python dictionary. A script in Bonsai or Blender can read it. | Click and your browser saves a text file of your settings for Blender users. They can read it in a script. | Click the button when you port a setup to the Blender implementation. | Report: Rendering in Bonsai/Blender |
| Reset to defaults | The button sets all settings back to the defaults of the report. It clears your pins, hides and class edits. | Click and every slider and switch returns to its starting value. Your protected and removed parts and style changes vanish too. | Click the button to start again from a known state. Export your settings first. | Report: Parameters and defaults |

## Panel dock

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Panel dock* | The dock holds this panel at the right edge of the window. It folds into a narrow rail. | The settings area sits on the right and can fold into a thin strip. A folded strip gives the picture more room. | Fold the dock to gain view area. Unfold it to change a setting. | Report: Onboarding checklist |
| Collapse toggle | The button folds the settings panel into a narrow rail and opens it again. The 3D view uses the freed width. | Click and the settings area shrinks to a thin strip, so the picture gets wider. Click again and it opens. | Click the button to gain view area. Press the ] key for the same action. | Report: Onboarding checklist |

## Sidebar

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sidebar* | The sidebar shows the model tree, the selection sets and the properties of the selected object. | The left side lists the parts of the building and your saved groups. Pick a part to see it light up. | Click an item to select it. Use the eye icon to hide it. | Report: Onboarding checklist |
| Collapse toggle | The button folds the sidebar into a narrow rail and opens it again. The 3D view uses the freed width. | Click and the left side shrinks to a thin strip, so the picture gets wider. Click again and it opens. | Click the button to gain view area. Press the [ key for the same action. | Report: Onboarding checklist |
| Model tab | The tab shows the model tree. The tree groups objects by storey and by class. | Click and the left side lists the parts of the building, grouped by level and kind. | Click the tab to browse the model. Open a group to see its objects. | Report: Onboarding checklist |
| Sets tab | The tab shows the saved selection sets of this model. | Click and the left side shows your saved groups of parts. You can reuse a group in one click. | Click the tab to save, apply, export or import selection sets. | Report: Onboarding checklist |
| Filter box | The box filters the model tree by name, GlobalId or class. The count shows the matching objects. | Type a few letters and the list shrinks to the parts that match. A small number tells you how many match. | Type part of a name to find an object. Press Escape to clear the filter. | Report: Onboarding checklist |
| Eye icon | The icon hides or shows the object or the group of its row. A hidden object is also a user hide. | Click and the part, or the whole group, disappears from the picture. Click again and it returns. | Click the icon to hide a row. Click it again to show the row. | Report: Appendix C, pin sources |
| Bucket dot | The dot shows the bucket of the object after classification. The buckets are focus, host, near and far. | The small mark tells you why a part looks the way it does. Blue means picked, red means crossed, amber means close and grey means distant. | Read the dot to see why an object ghosts. Select a duct to see the dots change. | Report: Terminology |
| Expand arrow | The arrow opens or closes a group in the model tree. | Click and the group opens to show the parts inside it. Click again and it closes. | Click the arrow to show the objects of the group. | Report: Onboarding checklist |
| Set name box | The box holds the name for a new selection set. | Type a label for a new saved group here. The label shows in the list after you save. | Type a name. Press Enter to store the set. | Report: Onboarding checklist |
| Save selection | The button stores the current selection as a new set with the typed name. | Click and the viewer stores the parts you picked as a named group. The group appears in the list below. | Select the objects. Type a name. Click the button to save. | Report: Onboarding checklist |
| Export sets | The button downloads the selection sets of this model as a JSON file. | Click and your browser saves a small file with all your saved groups. Keep it as a backup or send it to a colleague. | Click the button to back up the sets or to share them. | Report: Onboarding checklist |
| Import sets | The button loads selection sets from a JSON file. A set with the same name is replaced. | Click, pick a file of saved groups, and they join your list. The new group takes the place of an old one with the same name. | Click the button. Select a file. | Report: Onboarding checklist |
| Apply set | The button replaces the selection with the objects of the set and frames them. | Click and the parts of that group become your picked items, and the picture moves to show them. | Click the button to jump to a saved view of the model. | Report: Onboarding checklist |
| Add set | The button adds the objects of the set to the current selection. | Click and the parts of that group join the items you already picked. The picked area grows. | Click the button to build a larger focus from several sets. | Report: Onboarding checklist |
| Update set | The button replaces the objects of the set with the current selection. | Click and the group now holds the parts you picked at this moment. Its old parts drop out. | Select the new objects. Click the button to overwrite the set. | Report: Onboarding checklist |
| Rename set | The button changes the name of the set. | Click, type a new label, and press Enter. The group keeps its parts and gets the new label. | Click the button. Type a new name. Press Enter. | Report: Onboarding checklist |
| Delete set | The button removes the set from the list. The objects stay in the model. | Click and the group disappears from the list. The parts stay in the building. | Click the button only when you no longer need the set. | Report: Onboarding checklist |
| Copy GlobalId | The button copies the GlobalId of the first selected object to the clipboard. | Click and the unique code of the picked part goes onto the clipboard. Paste it into another program to find the same part. | Select an object. Click the button and paste the id into your BIM tool. | Report: Onboarding checklist |
| New criteria set | The button opens an editor for a criteria set. A criteria set holds rules, and the viewer finds the matching objects. | Click and a small form opens. You describe the parts you want, such as outside walls, and the list fills itself. | Click the button. Add conditions or type a query. Click Save set. | Report: Onboarding checklist |
| Set filter box | The box shows only the selection sets whose name or query contains the typed text. | Type a few letters and the long list shrinks to the groups that match. Clear the text to see every group again. | Type part of a name. Press the Down arrow key to move into the list. Press Escape to clear the text. | Report: Onboarding checklist |
| Set menu | The button opens the actions of the set: update, rename, edit criteria, duplicate and delete. | Click and a short list of choices drops down for this saved group. Pick a choice to change or copy the group. | Click the button or press Enter. Use the arrow keys to move. Press Escape to close. | Report: Onboarding checklist |
| Criteria badge | The funnel icon marks a criteria set. The viewer finds its objects again from its query on each model load and each apply. | This group keeps itself up to date. When the building changes, the group picks up the new matching parts. | Hover the icon to read the query. Open the set menu to edit the query. | Report: Onboarding checklist |
| Re-evaluate set | The menu item runs the query of the criteria set again and stores the objects that match now. | Click and the group checks the building again. Parts that now fit join it, and parts that no longer fit leave it. | Click the item after a change to the model or to its properties. | Report: Onboarding checklist |
| Edit criteria | The menu item opens the criteria editor with the query and the name of the set. | Click and the form opens with the rules of this group. Change a rule and the count updates as you type. | Click the item. Change the conditions or the query. Click Save changes. | Report: Onboarding checklist |
| Duplicate set | The menu item adds a copy of the set below it, with the word copy after the name. | Click and a twin of this group appears under it. You can change the twin and keep the first group intact. | Click the item before you change a set, to keep the old version. | Report: Onboarding checklist |
| Criteria set name | The box holds the name of the criteria set. | Type a label here. The label shows in the list of saved groups after you save. | Type a short name that says what the rules find. | Report: Onboarding checklist |
| Match all or any | The list sets how the conditions combine. The value all needs every condition. The value any needs at least 1 condition. | Choose all and a part must meet every rule. Choose the second choice and a part needs to meet only a single rule. | Select all to narrow the result. Select any to widen it. | Report: Onboarding checklist |
| Add condition | The button adds an empty condition row to the builder. | Click and a new blank rule appears. Fill it in to narrow or widen the result. | Click the button. Pick a field, an operator and a value. | Report: Onboarding checklist |
| Condition field | The box names the attribute or the property that the condition tests. The list offers the columns of this model. | Start to type and a list suggests what the parts of this building carry, such as a fire rating. | Type part of a name. Select a column from the list. | Report: Onboarding checklist |
| Condition operator | The list sets the comparison of the condition. LIKE matches a pattern, IN matches a list and IS NULL matches a missing value. | Pick equal to keep exact matches, or a pattern choice to find names that start or end with some text. | Select = for an exact value. Select LIKE and type % as a wildcard. | Report: Onboarding checklist |
| Condition value | The box holds the value that the condition compares with. The list suggests the values found in this model, most frequent first. | Start to type and the box suggests the entries that the parts really have, the common ones at the top. | Type or select a value. Separate the items of an IN list with commas. | Report: Onboarding checklist |
| Query box | The box holds the query text in a subset of SQL. The builder rows write this text, and you can edit it directly. | Power users can type the rules by hand here. A red message points at the exact spot of a typing mistake. | Type conditions with AND, OR and NOT. Put property names in double quotes. Press Ctrl+Enter to save. | Report: Onboarding checklist |
| Preview matches | The button selects and frames the objects that match the query, without a save. | Click and the parts that fit the rules light up, so you can check them before you keep the group. | Click the button to check the result. Change the rules if needed. | Report: Onboarding checklist |
| Save criteria set | The button stores the criteria set with its name and query. The set list shows it with a funnel icon. | Click and the group joins your list. It keeps its rules, so it stays current when the building changes. | Enter a name. Fix any error. Click the button. | Report: Onboarding checklist |
| Property menu | The button opens actions for this row: select by value or by presence, copy the value, save a criteria set. | Click, or right-click the row, to pick every part with the same entry, such as all outside walls. | Click the button or right-click a row. Pick an action. | Report: Onboarding checklist |
| Views tab | The tab shows the saved views of this model. A saved view keeps the camera, the cuts, the modes and the selection. | Click and the left side lists your bookmarked camera angles with their cuts and looks. One click brings a shot back. | Click the tab to save, restore, play, share or reorder views. | Report: Onboarding checklist |
| View name box | The box holds the name for the next saved view. An empty box gives the names View 1, View 2 and so on. | Type a label for the next bookmark here. Leave it empty and the app numbers the bookmarks for you. | Type a name. Press Enter to save the view. | Report: Onboarding checklist |
| Save view | The button stores the current state as a new view. The view keeps the camera, the cuts, the modes, the selection and the hides. | Click and the app keeps this camera angle, the cuts and the look as a bookmark with a small picture. | Set up the camera, the cuts and the modes. Click the button or press Ctrl+Shift+S. | Report: Onboarding checklist |
| Play views | The button steps through the saved views in list order. Each view stays on screen for the dwell time. | Click and the camera glides from one bookmark to the next, like a slide show. Press Escape to stop. | Click the button to present the views. Click it again, press Escape or click the model to stop. | Report: Onboarding checklist |
| View dwell time | The list sets how long each view stays on screen while the views play. | Pick a short value for a quick tour or a long value to talk about each bookmark. | Select a number of seconds before you start to play. | Report: Onboarding checklist |
| View grid toggle | The button switches the list between 1 line per view and a grid of thumbnails. | Click and the list turns into small pictures, so you can spot a shot at a glance. Click again for the short rows. | Click the button on a phone or when the names alone do not help. | Report: Onboarding checklist |
| Export views | The button downloads the saved views of this model as a JSON file with thumbnails. | Click and your browser stores a small file with all your bookmarks. Send it to a colleague or keep it as a backup. | Click the button to back up or share the views. | Report: Onboarding checklist |
| Import views | The button adds views from a JSON file. A view with the same id replaces the older copy. | Pick a file from a colleague and their bookmarks join your list. Your own bookmarks stay. | Click the button and select a views file. | Report: Onboarding checklist |
| View filter box | The box filters the list of views by name or preset id. | Type a few letters and the list shrinks to the bookmarks that match. A small number tells you how many match. | Type part of a name. Press Escape to clear the box. | Report: Onboarding checklist |
| Restore view | The name restores the view. The camera moves smoothly to the stored pose and the stored state comes back. | Click and the camera glides back to the stored angle. The cuts, the look and the picked parts return too. | Click a name to go back to the view. Press Shift+PageUp or Shift+PageDown to step through the views. | Report: Onboarding checklist |
| View menu | The menu holds the commands for 1 view: update, rename, duplicate, copy link, BCF topic and delete. | Click and a short list of extra commands opens for this bookmark. | Click the button. Select a command. | Report: Onboarding checklist |
| View drag handle | The handle moves a view to a new place in the list. The play order follows the list. | Grab the dots and pull the row up or down to change the order of the slide show. | Drag the handle to a new place. Press Alt+ArrowUp or Alt+ArrowDown on a row for the same move. | Report: Onboarding checklist |
| Update view | The command replaces the stored state of the view with the current state. The name stays. | Click and the bookmark takes on the camera angle and look you have now, with a fresh picture. | Adjust the camera or the cuts. Then click the command. | Report: Onboarding checklist |
| Rename view | The command changes the name of the view. | Click and you can type a new label for the bookmark. Press Enter to keep it. | Type the new name. Press Enter to accept or Escape to cancel. | Report: Onboarding checklist |
| Duplicate view | The command makes a copy of the view below it. | Click and a second bookmark appears right under this one. Change the copy and keep the original. | Click the command, then update the copy. | Report: Onboarding checklist |
| Copy view link | The command copies a link that opens the viewer in this view. The link holds the view itself, not the thumbnail. | Click and a web address lands on your clipboard. A colleague who opens it sees the same camera angle and look. | Click the command. Paste the link into a chat or an email. | Report: Onboarding checklist |
| View as BCF topic | The command restores the view and creates a BCF topic with a snapshot from it. | Click and the app turns this bookmark into an issue with a picture, ready to send to another design tool. | Click the command. Open the Issues tab to add comments or to export the topic. | Report: Onboarding checklist |
| Delete view | The command removes the view from the list. The command asks for a second click. | Click twice and the bookmark disappears from the list for good. | Click the command 2 times to remove the view. | Report: Onboarding checklist |

## View modes

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: View modes* | The folder holds the 2 cutaway views, behind only and peelback. Both cut the context per pixel and never cut the focus. | These controls cut holes in whatever hides the selected item. You can use one cut at a time or both together. | Select an object first. Open a sub folder to change a cut. | Report: Appendix F, View modes |

## Behind only

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Behind only* | The folder controls the behind-only view. A plane across the line of sight removes or fades the context in front of the focus. | These controls take away the walls and slabs between you and the selected item. What lies past it stays solid. | Select an object. Turn the view on. Change the offset to keep more or less solid context around the focus. | Report: Appendix F, View modes |
| enabled | The switch turns the behind-only view on or off. It needs a selected object. Press the B key for the same action. | On: the walls and slabs in the way vanish or fade, so you see past them. Off: nothing is cut. | Select an object. Turn the switch on to see what lies past it. | Report: Appendix F, View modes |
| front treatment | The list sets what happens to the context in front of the cut plane. The value cut removes it. The value ghost fades it. The value cut + cap removes it and paints flat caps. | Choose cut and the blockers vanish. Choose the second and they turn faint but stay. Choose the third and solid parts look sliced open with a hatched face. | Select cut for a clean picture of the back. Select ghost to keep a faint sense of place. Select cut + cap to see solids as sections. Press Shift+B to cycle. | Report: Appendix F, View modes |
| offset (m) | The slider moves the cut plane toward the camera by this distance in metres. A negative value cuts into the focus. | Move the slider right and a thicker shell of walls and slabs stays around the selected item. Move it left and the cut gets closer, then goes inside the item. | Increase the value to keep more solid context around the focus. Decrease the value to cut closer. Use a negative value to cut into the focus. | Report: Appendix F, View modes |
| front alpha | The slider sets the alpha of the context in front of the plane for the ghost treatment. | Move the slider left and the parts in the way turn almost invisible. Move it right and they stay solid. It acts on the faint choice alone. | Increase the value to keep the blockers more visible. Decrease the value to fade them more. | Report: Appendix F, View modes |
| orientation | The list sets the direction of the cut plane. The value camera follows the view. The value locked freezes the plane. The value horizontal cuts a plan. | Choose camera and the cut turns as you orbit. Choose locked and it stays put while you orbit. Choose horizontal and it slices flat from above, like a plan drawing. | Select camera to cut along your line of sight. Select locked to freeze the plane. Select horizontal for a plan cut. | Report: Appendix F, View modes |
| apply to | The list sets which context objects the cut affects. The value all context cuts every context object. The value occluders only cuts the occluders. | Choose the first and every wall and slab in the way gets cut. Choose the second and just the parts that really block the selected item get cut. | Select all context for a clean picture. Select occluders only to keep the rest of the building intact. | Report: Appendix F, View modes |
| keep x-ray behind | The switch keeps the sightline alpha of the context behind the plane. When it is off, that context draws fully solid. | On: parts past the cut still fade where they block the view. Off: everything past the cut turns solid. | Turn the switch on to keep the x-ray look behind the plane. Turn it off to get solid structure behind the focus. | Report: Appendix F, View modes |
| cap colour | The colour picker sets the colour of the flat caps in the cut + cap treatment. | Pick a shade and the hatched faces that close the cut change to it. | Choose a colour that stands out from your model colours. | Report: Appendix F, View modes |

## Peelback

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Peelback* | The folder controls the peelback. A peel cuts a window through the context in front of the focus. The window follows the outline of the focus. | These controls cut a hole in the walls and slabs in front of the selected item. The rest of each wall stays in place. | Select an object. Turn the peelback on. Change the radius to make the window larger or smaller. | Report: Appendix F, View modes |
| enabled | The switch turns the peelback on or off. It needs a selected object. Press the P key for the same action. | On: a window opens in the walls and slabs in front of the selected item. Off: nothing is cut. | Select an object. Turn the switch on to open a window to it. | Report: Appendix F, View modes |
| radius (m) | The slider sets the radius of the peel window at the depth of the focus, in metres. | Move the slider right and the hole around the selected item grows. Move it left and the hole shrinks to a thin outline. | Increase the value to see more of the surroundings. Decrease the value to keep more of the walls. Press Alt+= or Alt+- to change it by 25 percent. | Report: Appendix F, View modes |
| slope | The slider sets how much the window radius grows for each metre between the surface and the focus. | Move the slider right and the hole widens toward you, like a cone. At 0 the hole keeps the same width. | Increase the value for a wide opening at the surface. Set the value to 0 for a straight tunnel. | Report: Appendix F, View modes |
| feather (m) | The slider sets the width of the soft edge of the window, in metres. | Move the slider right and the hole gets a soft, fading border. At 0 the border is sharp. | Increase the value for a smooth edge. Decrease the value for a crisp edge. | Report: Appendix F, View modes |
| rim band | The switch draws a band of the accent colour on the surface at the edge of the window. | On: a coloured ring marks the border of the hole. Off: the border has no mark. | Turn the switch on to find the window quickly. Turn it off for a clean look. | Report: Appendix F, View modes |
| rim colour | The colour picker sets the colour of the rim band. | Pick a shade and the ring around the hole changes to it. | Choose a colour that stands out from your model colours. | Report: Appendix F, View modes |
| cap colour | The colour picker sets the colour of the flat caps on the revealed back faces inside the window. | Pick a shade and the flat faces inside the cut change to it. | Choose a colour that stands out from your model colours. | Report: Appendix F, View modes |
| outside | The list sets how the context outside the window looks. The value x-ray keeps the x-ray result. The value solid draws it fully solid. | Choose the first and the rest of the building keeps fading around the hole. Choose solid and everything around the hole looks solid. | Select x-ray to combine the peel with the fading. Select solid to see the peel alone. | Report: Appendix F, View modes |
| apply to | The list sets which context objects the peel affects. The value all context affects every context object. The value occluders only affects the occluders. | Choose the first and every wall and slab in front gets a hole. Choose the second and just the parts that really block the selected item get one. | Select all context for a clean window. Select occluders only to keep the rest of the building intact. | Report: Appendix F, View modes |
| animate | The switch grows the window radius from 0 over 500 ms when the peel starts or when the selection changes. | On: the hole grows smoothly each time. Off: the hole appears at once. | Turn the switch on for a smooth reveal. Turn it off for screenshots. | Report: Appendix F, View modes |

## Model cleanup

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Model cleanup* | The folder finds debris in the model and hides it. The hide is reversible and the viewer does not change the model file. | These controls find stray bits, such as loose pieces and tiny parts, and tuck them out of sight. You can bring them back. | Set the rules. Click Preview matches to check them. Click Hide matches to hide them. | Report: Appendix H, Model cleanup |
| Preview matches | The button tints the matches magenta. The viewer frames them when fewer than 50 elements match. | Click and the pieces that the rules found turn pink, so you can check them before you hide them. | Set the rules first. Click the button. Use Select matches when a match hides inside a wall. | Report: Appendix H, Model cleanup |
| Hide matches | The button hides the matches and records which ids it hid. The model file does not change. | The found pieces vanish from the picture. No part gets deleted. | Click Preview matches first. Click the button to hide the matches. | Report: Appendix H, Model cleanup |
| Restore cleanup | The button shows again only the elements that the cleanup hid. Elements that you hid yourself stay hidden. | The pieces that this tool hid come back. Parts that you hid by hand stay out of sight. | Click the button to undo the hide of the matches. | Report: Appendix H, Model cleanup |
| Select matches | The button selects all matches, so that you can find them in the sidebar and frame them. | Click and the found pieces light up as your picked group, even those that sit inside walls. | Click the button when a match hides inside another object. | Report: Appendix H, Model cleanup |
| Export report | The button downloads a JSON file with the ids, GlobalIds, classes, names and reasons of the matches. | Click and a file of the found pieces, with the reason for each, lands in your downloads. | Click the button to share the list with other people. | Report: Appendix H, Model cleanup |
| Cleanup status | The read-only field shows the result of the last cleanup step. | A short text tells you how many pieces the rules found or hid. | Read the line after each step. | Report: Appendix H, Model cleanup |
| apply on load | The switch runs the cleanup rules and hides the matches each time a model loads. | On: the debris is gone as soon as a building appears. Off: you decide when to hide it. | Turn the switch on for models that always need the same clean up. | Report: Appendix H, Model cleanup |
| length unit | The list sets the unit of every length limit of the cleanup. The choices are mm, cm and m. The rules keep metres. | Choose mm and the sizes and gaps show in millimetres. Choose m and they show in metres. The result stays the same. | Select mm for small parts such as fasteners. Select m for distances across the site. | Report: Appendix H, Model cleanup |

## Floating

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Floating* | The folder holds the rule for floating elements. A floating element does not touch the main structure and is smaller than the limit. | This rule finds small pieces that hang in the air away from the rest of the building. | Turn the rule on. Choose how to measure size. Set the limit. Click Preview matches. | Report: Appendix H, Model cleanup |
| enabled | The switch turns the floating rule on or off. | On: small loose pieces count as debris. Off: this rule finds nothing. | Turn the switch on to find pieces that hang away from the building. | Report: Appendix H, Model cleanup |
| size metric | The list sets how the rule measures size. The choices are largest dimension, bounds volume, mesh volume and triangle count. | Each choice changes what small means. Length judges the longest side. Volume judges the space a part fills. Triangle count judges the detail. | Select largest dimension for most models. Select a volume for thin, long parts. Select triangle count for mesh detail. | Report: Appendix H, Model cleanup |
| threshold | The slider sets the size limit of the floating rule. A part below the limit matches. The unit follows the size metric and the length unit. | Move the slider right and bigger loose pieces count as debris. Move it left and only the tiny ones count. | Increase the value to catch larger pieces. Decrease the value to keep more of the model. | Report: Appendix H, Model cleanup |
| mode | The list sets what the rule matches. The value single elements matches elements with no contact. The value small clusters matches whole small groups. | Choose the first and only pieces that touch nothing match. Choose clusters and whole small groups of touching pieces match. | Select single elements for lone pieces. Select small clusters for small groups of pieces. | Report: Appendix H, Model cleanup |
| contact tolerance (m) | The slider sets the largest gap at which 2 elements still count as touching. The length unit list sets the unit. | Move the slider right and pieces with a small gap between them count as joined. At 0 they must touch exactly. | Increase the value if the model has small gaps between parts. Decrease the value for exact contact. | Report: Appendix H, Model cleanup |
| precise contacts | The switch checks the real mesh distance and not only the bounding boxes of 2 elements. | On: a part that sits close to a curved wall counts as loose if it does not truly touch it. Off: the box around the wall counts as touching. | Turn the switch on if curved or diagonal parts hide debris. Turn it off for speed. | Report: Appendix H, Model cleanup |

## Tiny

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Tiny* | The folder holds the rule for tiny elements. An element is tiny when its largest side is below the limit. | This rule finds very small parts, such as screws or specks, that you can hardly see. | Turn the rule on. Set the largest side. Pick mm, cm or m in the length unit list. | Report: Appendix H, Model cleanup |
| enabled | The switch turns the tiny rule on or off. | On: very small parts count as debris. Off: this rule finds nothing. | Turn the switch on to find specks and small fasteners. | Report: Appendix H, Model cleanup |
| max size (m) | The slider sets the largest side that a tiny element may have. The length unit list sets the unit. | Move the slider right and bigger bits count as debris. Move it left and only specks count. | Increase the value to match more small parts. The default is 0.05 m, which is 50 mm. | Report: Appendix H, Model cleanup |

## Distant strays

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Distant strays* | The folder holds the rule for distant strays. A stray lies much further from the model centre than the rest of the model. | This rule finds objects that sit way off from the building, such as markers left at the wrong place. | Turn the rule on. Increase the factor or the min gap if the rule matches too many objects. | Report: Appendix H, Model cleanup |
| enabled | The switch turns the distant strays rule on or off. | On: objects that sit way off from the building count as debris. Off: this rule finds nothing. | Turn the switch on to find markers and objects at the origin. | Report: Appendix H, Model cleanup |
| distance factor | The slider sets the factor k. A bounds centre further than k times the robust radius from the median centre matches. | Move the slider right and an object must sit much further out to count as lost. Move it left and more objects count. | Increase the value to match fewer objects. The default is 6. | Report: Appendix H, Model cleanup |
| min gap (m) | The field sets the smallest distance between a stray and the box of the main model. The value 0 turns the limit off. | Raise the value and only objects well outside the building count as lost. At 0 the factor alone decides. | Set the value to a distance that you trust, such as 50 m. Keep 0 to use the factor only. | Report: Appendix H, Model cleanup |
| max size (m) | The field sets the largest side that a stray may have. A larger object never matches. The value 0 accepts any object. | Set a small value and only little markers out on their own count as lost. At 0 big lost parts count too. | Set the value to keep large misplaced parts, such as a site model, out of the matches. | Report: Appendix H, Model cleanup |

## Duplicates

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Duplicates* | The folder holds the rule for duplicate elements. Duplicates have the same class, the same triangle count and the same bounds. | This rule finds copies that lie on top of each other and flicker when you look at them. | Turn the rule on to hide the extra copies. Check the preview before you hide. | Report: Appendix H, Model cleanup |
| enabled | The switch turns the duplicate rule on or off. The lowest id stays and the others match. | On: extra copies on the same spot count as debris, and the first copy stays. Off: this rule finds nothing. | Turn the switch on to remove flicker from copies that lie on top of each other. | Report: Appendix H, Model cleanup |

## Degenerate

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Degenerate* | The folder holds the rule for degenerate elements. A degenerate element has no triangles, a broken bound or a class that is not physical. | This rule finds empty or broken parts that draw nothing useful, plus labels and grid lines that slipped in. | Turn the rule on. Keep it on for most models. | Report: Appendix H, Model cleanup |
| enabled | The switch turns the degenerate rule on or off. | On: empty or broken parts count as debris. Off: this rule finds nothing. | Turn the switch on to find parts that draw nothing useful. | Report: Appendix H, Model cleanup |

## Model cleanup/Classes

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Model cleanup/Classes* | The folder holds quick switches for whole groups of classes. Each switch matches every element of the listed classes. | These switches remove whole kinds of parts at once, such as furniture or screws. | Turn a switch on to match that group. Click Preview matches to check the result. | Report: Appendix H, Model cleanup |
| proxies | The switch matches every IfcBuildingElementProxy element. | On: generic parts with no clear kind count as debris. Off: they stay. | Turn the switch on if the model holds many unnamed generic parts. | Report: Appendix H, Model cleanup |
| furniture | The switch matches every IfcFurnishingElement, IfcFurniture and IfcSystemFurnitureElement element. | On: tables, chairs and other room fittings count as debris. Off: they stay. | Turn the switch on to remove furniture from a services review. | Report: Appendix H, Model cleanup |
| accessories and fasteners | The switch matches every IfcDiscreteAccessory, IfcFastener and IfcMechanicalFastener element. | On: small bolts, clips and fittings count as debris. Off: they stay. | Turn the switch on to remove small hardware from the picture. | Report: Appendix H, Model cleanup |

## Hover info

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Hover info* | The folder controls the info card that follows the pointer. The card names the element and lists some of its properties. | These controls decide when a small card with facts appears next to the mouse, and what it tells you. | Rest the pointer on an element. Hold Alt to freeze the card. Press the I key to switch the card on or off. | Report: Appendix L, Hover info and properties |
| show on hover | The switch turns the hover card on or off. Press the I key for the same action. | On: a small card with facts appears when the mouse rests on a part. Off: no card appears. | Turn the switch off if the card gets in your way. | Report: Appendix L, Hover info and properties |
| delay (ms) | The slider sets the rest time in milliseconds before the card appears. | Move the slider right and you wait longer for the card. At 0 it appears at once. | Increase the value if the card appears too often. The default is 350 ms. | Report: Appendix L, Hover info and properties |
| max rows | The slider sets the number of property rows on the card, from 0 to 24. | Move the slider right and the card lists more facts. At 0 it shows the name only. | Increase the value to read more facts. Decrease the value for a small card. | Report: Appendix L, Hover info and properties |
| show x-ray state | The switch adds a footer line with the bucket and the alpha of the element. The line shows only while x-ray is on. | On: the card also tells you how much the part fades and why. Off: the card leaves that line out. | Turn the switch on to learn why a part looks faded. | Report: Appendix L, Hover info and properties |
| highlight | The switch outlines the hovered element while the card shows. | On: the part under the mouse gets a bright outline. Off: it looks as usual. | Turn the switch on to see which part the card describes. | Report: Appendix L, Hover info and properties |
| property filter | The text box lists patterns, in priority order, that choose the rows of the card. Patterns match the whole key and ignore case. The default list covers object type, external flag, load bearing, fire rating and reference. It also covers length, width, height and net volume in quantity sets. The set name must start with Qto or end with Quantities. | Type the names of the facts that you care about and the card shows those first. A star stands for any text. | Separate patterns with commas. Use * for any run of characters. If no pattern matches an element, the card shows its first rows. | Report: Appendix L, Hover info and properties |
| all properties in sidebar | The switch lists every property of the first selected element in the sidebar, and not only the filtered ones. | On: the side list shows all the facts of the picked part. Off: it shows the short list. | Turn the switch on to read every fact. Turn it off to read the short list. | Report: Appendix L, Hover info and properties |

## Presets

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Presets* | The folder holds the preset controls. A preset is a named look that sets many settings in 1 step. | These controls switch the whole picture to a ready-made look with one click. You can also save your own looks. | Choose a name. Click Apply preset. Press a key from 1 to 9 for the same action. | Report: Appendix I, Presets and keyboard |
| preset | The list selects the preset to apply. The built-in presets come first and your own presets follow. | Pick a name from the list. The picture stays the same until you click the Apply button. | Select a name. Click Apply preset. | Report: Appendix I, Presets and keyboard |
| Apply preset | The button applies the chosen preset. The model, the selection and the camera stay as they are. | Click and many settings jump to the chosen look in one step. The building and your camera stay put. | Select a preset first. Click the button. Press a key from 1 to 9 for the first 9 presets. | Report: Appendix I, Presets and keyboard |
| Save current as preset | The button opens the Presets tool with a form. The form stores the current settings under a name. | Click and a form lets you name the picture that you set up. You can return to it with one click. | Set up the picture. Click the button. Type a name. Tick the sections to store. | Report: Appendix I, Presets and keyboard |
| Export presets | The button downloads your own presets as a JSON file. The built-in presets are not in the file. | Click and your saved looks go into a file that you can keep or send to a colleague. | Save at least 1 preset first. Click the button. | Report: Appendix I, Presets and keyboard |
| Import presets | The button adds presets from a JSON file. Imported presets always become your own presets. | Click and pick a file of looks. They join your list. | Click the button. Choose a file from a colleague. Read the status line for problems. | Report: Appendix I, Presets and keyboard |
| Preset status | The read-only field names the active preset, or the settings that a preset skipped. | A short text tells you which look is on now. It also lists parts that did not apply. | Read the line after you apply a preset. | Report: Appendix I, Presets and keyboard |

## Top bar

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Top bar* | The folder holds the setting of the thin strip at the top of the view. The strip holds 5 mode buttons and the search box. | This setting shows or hides the thin strip above the picture. The picture itself does not change. | Open the folder. Use the switch to show or hide the strip. | Report: Appendix I, Presets and keyboard |
| Show top bar | The switch shows or hides the top bar. The setting is topBar.visible in the parameter document. | On: a thin strip with the mode buttons and the search box sits above the picture. Off: the picture uses the full height. | Turn the switch off for a clean picture. Press Shift+T for the same action. | Report: Appendix I, Presets and keyboard |
| Solid | The button applies the Solid preset. Every element is drawn opaque. X-ray, view modes, imaging, glow and auto orbit turn off. Section cuts and clearance stay. | The whole model shows with no see-through parts, except real glass. A cut you made stays cut. | Click the button. Press Shift+0 for the same action. A second click does nothing. | Report: Purpose |
| Ghost | The button applies the Coordination preset. This is the classic X-ray view. The objects that block the selection fade. | The walls and slabs in front of the selected item turn see-through. The selected item stays solid and clear. | Select an object. Click the button. Click it again to switch to Solid. Press Shift+1 for the same action. | Report: Purpose |
| Radiograph | The button applies the Radiograph preset. The picture looks like a medical X-ray image of the model. | The picture turns dark with blue and white tones. Dense parts glow and thin parts fade. The selected item shines like a bone. | Select an object. Click the button. Click it again to switch to Solid. Press Shift+2 for the same action. | Report: Appendix G, Imaging and sectioning |
| Glow | The button applies the Focus glow preset. It turns on the bloom and the edge glow for the focus. | The selected item gets a soft halo and a bright outline. You find it fast, even in a large model. | Select an object. Click the button. Click it again to switch to Solid. Press Shift+3 for the same action. | Report: Terminology, focus |
| Cutaway | The button applies the Peel only preset. It cuts a window through the objects that block the view of the selection. | A round hole opens in the walls and the roof in front of the selected item. The rest of the building stays solid. | Select an object. Click the button. Click it again to switch to Solid. Press Shift+4 for the same action. | Report: Appendix F, View modes |

## Penetrations

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Penetrations* | The folder controls the penetration schedule. A penetration is a place where an MEP element passes through a structural host. | These controls list where pipes and ducts go through slabs and walls, and tell you if a cut-out is ready. | Click Analyse penetrations. Choose the scope. Click Export penetrations CSV to save the list. | Report: Appendix J, Coordination tools |
| Analyse penetrations | The button runs the analysis. It finds where MEP elements cross structural hosts and sets the opening status of each crossing. | Click and the viewer builds a list of places where pipes and ducts go through slabs and walls. Round dots mark them on the model. | Click the button after you change the scope or the model. Open the Penetrations tool to read the list. | Report: Appendix J, Coordination tools |
| Export penetrations CSV | The button downloads the filtered rows as a CSV file. | Click and the list that you see goes into a spreadsheet file. | Click Analyse penetrations first. Filter the rows in the drawer. Click the button. | Report: Appendix J, Coordination tools |
| scope | The list sets which MEP elements the analysis tests. The value focus classes tests all MEP elements. The value focus only tests the focus set. | Choose the first and every pipe and duct in the building gets checked. Choose the second and only the picked run gets checked. | Select focus classes for a full schedule. Select focus only to check a single run. | Report: Appendix J, Coordination tools |
| markers | The switch draws a coloured marker at each listed crossing. | On: coloured dots sit on the building at each crossing. Off: the dots disappear. | Turn the switch off if the dots hide your view. | Report: Appendix J, Coordination tools |
| Penetration status | The read-only field shows the counts by opening status and the time of the analysis. | A short text counts the crossings with a cut-out, without one and not known. | Read the line after each analysis. | Report: Appendix J, Coordination tools |

## Measure

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Measure* | The folder controls the measure tool. The tool shows the distance between 2 points or between 2 elements. | These controls let you click on the building and read a length in metres or millimetres. | Open the Measure tool in the action panel. Click 2 points on the model. | Report: Appendix J, Coordination tools |
| mode | The list sets what the tool measures. The value point to point measures between 2 surface points. The value element to element measures the shortest gap between 2 elements. | Choose the first and you click 2 spots on surfaces. Choose the second and you click 2 parts to read their closest gap. | Select point to point for a length. Select element to element for a gap between 2 parts. | Report: Appendix J, Coordination tools |
| units | The list sets the unit of the labels. The value m shows metres with 3 decimals. The value mm shows whole millimetres. | Choose metres and a length reads like 2.345. Choose millimetres and it reads like 2345. | Select mm for detail work. Select m for room sizes. | Report: Appendix J, Coordination tools |
| snap to vertices | The switch moves a click to the nearest vertex of the hit triangle when the vertex lies within 12 px. | On: your click jumps to the closest corner of the surface if one lies close. Off: the click lands exactly where you point. | Turn the switch on to measure from corner to corner. Turn it off to measure at any spot. | Report: Appendix J, Coordination tools |
| Clear measurements | The button deletes all dimension lines from the model. | Click and every dimension line disappears from the model. | Export the measurements first if you need them. Click the button to start again. | Report: Appendix J, Coordination tools |

## Clearance

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Clearance* | The folder controls the clearance colouring. The colouring shows the clearance of each context element to the focus. | These controls paint walls and slabs red, amber or blue by how close they sit to the selected item. | Select an object. Turn the colouring on. Set the limits for tight and ok. | Report: Appendix J, Coordination tools |
| enabled | The switch turns the clearance colouring on or off. The colouring needs a selected object. | On: walls and slabs turn red, amber or blue by how close they sit to the selected item. Off: the normal colours return. | Select an object. Turn the switch on. Read the legend at the bottom right. | Report: Appendix J, Coordination tools |
| tight (m) | The slider sets the distance in metres below which a context element counts as tight. | Move the slider right and more parts count as too close and show amber. Move it left and fewer do. | Increase the value to find narrow gaps early. The default is 0.05 m. | Report: Appendix J, Coordination tools |
| max range (m) | The slider sets the range in metres up to which the colouring reaches. Elements beyond the range keep their colour. | Move the slider right and parts that sit further away get a colour too. Move it left and only close parts get one. | Decrease the value to speed up the check. The default is 0.5 m. | Report: Appendix J, Coordination tools |
| Clearance status | The read-only field shows the number of elements in each band and the compute time. | A short text counts the red, amber and blue parts and says how long the check took. | Read the line after each change. | Report: Appendix J, Coordination tools |

## BCF

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: BCF* | The folder controls BIM Collaboration Format issues. A BCF topic stores a title, comments and viewpoints. | These controls read, write and share issue notes with other people in the project team. | Click Open BCF to read a file. Click Create topic from view to note a new issue. | Report: Appendix J, Coordination tools |
| Open BCF | The button opens a file picker for a BCF file. You can also drop a file on the page. | Click and pick an issue file from your computer. Its notes appear in the list. | Click the button. Choose a .bcf or .bcfzip file. | Report: Appendix J, Coordination tools |
| Create topic from view | The button asks for a title and details. It then stores a topic with a snapshot and a viewpoint of the current camera. | Click and fill in a short form. The app saves a note that remembers what you see now. | Frame the issue in the picture. Click the button. Fill in the form. | Report: Appendix J, Coordination tools |
| Export BCF 2.1 | The button downloads every topic as a BCF 2.1 file. | Click and all issue notes go into one file that most programs can read. | Select this version for the widest support. | Report: Appendix J, Coordination tools |
| Export BCF 3.0 | The button downloads every topic as a BCF 3.0 file. | Click and all issue notes go into one file in the newer layout. | Select this version when all partners read BCF 3.0. | Report: Appendix J, Coordination tools |
| Clear viewpoint | The button undoes what the viewpoint changed. It shows the elements that BCF hid and removes its colours and clip planes. | Click and the parts that an issue note hid come back with their normal colours and no cuts. Your camera stays. | Click the button after you review a topic. | Report: Appendix J, Coordination tools |
| BCF status | The read-only field shows what the last BCF step did, such as what applied and what it skipped. | A short text tells you what the last step did and what it had to skip. | Read the line after you apply a viewpoint. | Report: Appendix J, Coordination tools |

## Markup

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Markup* | The folder controls markup sets. A set is 1 saved view with clouds, notes, highlights and shapes. | These controls save a view, open a shared file and write a PDF for your team. | Click New markup set from view. Open the Markup tool to draw. | Report: Appendix J, Coordination tools |
| New markup set from view | The button saves the current view as a new markup set. | Click and the camera, cuts and look go into storage. You can draw at once. | Frame the view. Click the button. | Report: Appendix J, Coordination tools |
| Open markup file | The button opens a file picker for a markup PDF or JSON file. You can also drop a file on the page. | Click and the picture and the notes of the shared document come back. | Click the button. Choose the file. | Report: Appendix J, Coordination tools |
| Export markup PDF | The button downloads a PDF of all sets. The PDF shows the clean view, the marked view and a table of comments. | Click and you get a page file to print or to send. It also carries the data to restore the notes. | Click the button after you finish the markup. | Report: Appendix J, Coordination tools |
| Export markup JSON | The button downloads all sets as a JSON file. | Click and you get a small file. Drop it on the viewer to restore the view and the notes. | Click the button. Send the file with the model name. | Report: Appendix J, Coordination tools |
| Markup page size | The list sets the page size of the PDF. Both sizes are landscape. | The choice changes the paper of the next PDF. | Select A4 or Letter. | Report: Appendix J, Coordination tools |
| Markup view-locked in 3D | The list sets how a markup that is not attached to the model shows in 3D. It has 3 choices: near view and pin, pin only, hidden. | A drawing that only fits the angle where you made it shows in full there. Away from that angle it fades and leaves a small flag. | Select near view and pin. Select pin only to see pins at all times. Select hidden to hide them. | Report: Appendix J, Coordination tools |
| Markup status | The read-only field shows the last message of the Markup tool. | A short text tells you what the tool did or why it did not. | Read the line after each action. | Report: Appendix J, Coordination tools |
| Markup PDF resolution (dpi) | The list sets the picture quality of the PDF in dots per inch. Screen uses the pixels of your window. | A higher number gives sharper pages and a bigger file. | Select 200 for most prints. Select 300 for fine detail. | Report: Appendix J, Coordination tools |

## Sidebar/Issues tab

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sidebar/Issues tab* | The tab lists the issues and the sketches of this model. A switch at the top changes the list. | Click and the left side shows what your team must fix, and the drawings that show where. | Click the tab. Click an item to open it and bring its view back. | Report: Appendix J, Coordination tools |

## Issues panel

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Issues panel* | The panel holds the issue list, the sketch list and the detail of the chosen item. | This column shows what is wrong, who owns it and where it sits. | Pick Issues or Sketches. Search or filter. Click an item to read it. | Report: Appendix J, Coordination tools |

## Issues panel/Segments

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Issues panel/Segments* | The switch picks the list. Issues carry a status and comments. Sketches are saved views with drawings. Sheets hold the pages of PDF drawings. | Click and the column swaps between the problems of your team, the drawn views and the paper drawings. | Click Issues, Sketches or Sheets. | Report: Appendix J, Coordination tools |

## Issues panel/Phone sheet

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Issues panel/Phone sheet* | On a small screen the list and the detail rise from the bottom edge of the view. | The list leaves the top of the picture free. It steps aside while you draw. | Tap the cross to close the sheet. Tap Issues in the status bar to open it again. | Report: Appendix J, Coordination tools |

## Drawing toolbar

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Drawing toolbar* | The bar floats over the view while you draw on a sketch. It holds the tools, the colours, the line weights and Done. | This bar lets you mark a view with clouds, arrows, text and pen lines. It goes away when you press Done. | Pick a tool. Drag on the view. Press Done when the drawing is ready. | Report: Appendix J, Coordination tools |

## Sheet view

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view* | The area shows 1 page of a PDF drawing in place of the 3D picture. The model stays loaded under it. | This area shows the paper drawing, so that you can mark it for your team. | Drag to move the page. Scroll or pinch to zoom. Press Back to model to return. | Report: Appendix J, Coordination tools |

## Sheet view/Back to model

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Back to model* | The button closes the page and shows the 3D model again. | Click and the paper drawing goes away. The building picture returns as you left it. | Click the button. | Report: Appendix J, Coordination tools |

## Sheet view/Fit

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Fit* | The button scales the page so that the whole page shows in the window. | Click and the whole drawing shows at once, centred in the area. | Click the button after you zoom in too far. | Report: Appendix J, Coordination tools |

## Sheet view/Sketch

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Sketch* | The list picks the sketch that you draw on. A read-only sketch cannot change. | Pick one and your marks go into it. Pick the last choice to start a new one. | Pick a sketch from the list. | Report: Appendix J, Coordination tools |

## Sheet view/Draw

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Draw* | The button shows the drawing tools and lets you draw on the page. | Click and a bar of tools appears. Your marks stay when the bar goes. | Click the button. Pick a tool. Drag on the page. | Report: Appendix J, Coordination tools |

## Sheet view/Drawing toolbar

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Drawing toolbar* | The bar holds the tools, the colours and the line weights for the page. It has no tool that needs the 3D model. | Mark the page with clouds, arrows and text. The bar goes away when you press Done. | Pick a tool. Drag on the page. Press Done to finish. | Report: Appendix J, Coordination tools |

## Sheet view/Place in model

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Place in model* | The button opens a view with the sheet on the left and the plan of a storey on the right. You pick 2 points on the sheet and the same 2 in the model. | The drawing gets its spot in the building. Your marks then stick to the walls under them. | Click the button. Choose the storey. Click point A on the sheet, then A in the model, then B and B. Click Accept. | Report: Appendix J, Coordination tools |

## Sheet view/Model overlay

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Model overlay* | The toggle draws the model as thin lines over the sheet. The lines are the plan cut about 1.2 m above the storey. | You see the walls of the building on top of the drawing. If they match the drawing, the fit is right. | Click the toggle. Move the slider to fade the lines. A misfit number shows when you pick 3 or more points. | Report: Appendix J, Coordination tools |

## Sheet view/Overlay opacity

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheet view/Overlay opacity* | The slider sets how strong the model lines look over the sheet. | Slide left and the lines fade, so the drawing shows through. Slide right and they get stronger. | Move the slider. | Report: Appendix J, Coordination tools |

## Place in model

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Place in model* | The view fits a sheet to the model. The left side shows the sheet. The right side shows the plan of the chosen storey. A phone shows the 2 sides in turn. | The fit shows at once as the building lines over the drawing. Accept keeps it. Redo starts the points again. Cancel changes nothing. | Choose the storey. Click point A on the sheet and the same point in the model, then B. A third point gives a better fit. Or type the drawing scale and give the rotation. | Report: Appendix J, Coordination tools |

## Sheets/3D opacity

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Sheets/3D opacity* | The slider sets how see-through the placed sheets look in the 3D view. | Slide left and the drawing fades, so the building shows through. Slide right and the drawing gets stronger. | Move the slider after you turn on Show in 3D for a sheet. | Report: Appendix J, Coordination tools |

## Issues panel/View switch

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Issues panel/View switch* | The control shows a sketch in 3D, in plan or in section. It appears when a drawing sits on a part of the model. | Click Plan and the picture turns to a cut from above. Click Section for a cut from the side. Click 3D to go back. | Click 3D, Plan or Section. Your own cut returns when you click 3D. | Report: Appendix J, Coordination tools |

## Drawing toolbar/View switch

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Drawing toolbar/View switch* | The control shows the sketch in 3D, in plan or in section while you draw. It appears when a drawing sits on a part of the model. | Click Plan and the picture shows a cut from above, with your marks on the same part. Click Section for a cut from the side. | Click 3D, Plan or Section. Draw on any of them. | Report: Appendix J, Coordination tools |

## Status bar/Open issues

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Status bar/Open issues* | The button counts the open issues of this model. An issue is open until it is resolved or closed. | Click and the left side lists the problems that still need work. | Click the button. | Report: Appendix J, Coordination tools |

## Markup drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Markup drawer* | The heading names the Markup drawer. The drawer holds the sets, the drawing tools and the list of markups. | This panel lets you sketch on a saved view for your team without an issue topic. | Make a set. Pick a tool. Draw on the view. Export a PDF. | Report: Appendix J, Coordination tools |
| New set from view | The button saves the current view as a new markup set. | Click and a card appears in the list with a small picture. | Frame the view. Click the button. | Report: Appendix J, Coordination tools |
| Open file | The button opens a markup PDF or JSON file. | Click and the sheets of the shared document join the list. The first one comes back on screen. | Click the button. Choose the file. | Report: Appendix J, Coordination tools |
| Restore view | The button brings back the camera, cuts and look of the set. | Click and the model looks as it did when you made the card. | Click the button after you move the camera. | Report: Appendix J, Coordination tools |
| Export PDF | The button downloads a PDF of this set. It has the clean view, the marked view and the comment table. | Click and the viewer renders both pictures. The file carries the data to bring back the notes. | Click the button. Wait for the download. | Report: Appendix J, Coordination tools |
| Export JSON | The button downloads this set as a JSON file. | Click and you get a small file that brings back the notes on the same model. | Click the button. | Report: Appendix J, Coordination tools |
| PDF of all sets | The button downloads a single PDF with every set. | Click and each card gets its own pages in the file. | Click the button when you have more than 1 set. | Report: Appendix J, Coordination tools |
| Convert to BCF topic | The button makes a BCF topic from the set. The topic has the viewpoint, the annotations and the comments. | Click and the sheet joins the issue list. You can then send it as an issue file. | Click the button. Open the Issues tab to export it. | Report: Appendix J, Coordination tools |
| Delete set | The button removes the set and its markups from the session. | Click twice and the card is gone. Save a file first if you need it later. | Click the button. Click again to confirm. | Report: Appendix J, Coordination tools |
| Undo | The button undoes the last change to the markups. The keys are Ctrl+Z. | Click and the last change goes back. | Click the button or press Ctrl+Z. | Report: Appendix J, Coordination tools |
| Redo | The button repeats the change that you undid. The keys are Ctrl+Shift+Z. | Click and the change comes back. | Click the button or press Ctrl+Shift+Z. | Report: Appendix J, Coordination tools |
| Finish | The button ends a polyline or polygon with the corners so far. | Click and the shape stays on the view. | Click the button. You can also press Enter. | Report: Appendix J, Coordination tools |
| Cancel drawing | The button drops the corners that you placed. | Click and the unfinished shape disappears from the view. | Click the button. You can also press Escape. | Report: Appendix J, Coordination tools |
| Add comment | The button adds your comment to the chosen markup. | Click and your note shows with your name and the time. | Type the comment. Click the button. | Report: Appendix J, Coordination tools |
| Page size | The list sets the page size of the PDF. Both sizes are landscape. | The choice changes the paper of the next PDF. | Select A4 or Letter. | Report: Appendix J, Coordination tools |
| Show markups on the model | The tick shows or hides the markups of the active set. | Clear the tick and only the plain building remains. | Clear the tick to see the plain model. | Report: Appendix J, Coordination tools |
| Fill | The tick fills closed shapes with a light colour. | Tick it and clouds, rectangles, ellipses and polygons get a tint. | Tick it before you draw. Or select a shape and tick it. | Report: Appendix J, Coordination tools |
| Tool button | The button picks a drawing tool. Press the tool again to go back to Select. | The next drag or click on the picture makes that shape. | Click a tool. Draw on the view. | Report: Appendix J, Coordination tools |
| Colour swatch | The swatch sets the colour of the next markup or of the chosen item. | Each tool keeps its own hue. Clouds start red and highlights start yellow. | Click a colour. | Report: Appendix J, Coordination tools |
| Line weight | The button sets the line weight of the next markup or of the chosen item. | A higher number makes a thicker stroke. | Click a weight. | Report: Appendix J, Coordination tools |
| Attachment chip | The chip tells what the shape is attached to in 3D. A shape is attached to elements, a surface, a region, a measurement or a penetration. Else it is view-locked. | An attached shape stays on its target when you orbit. A view-locked shape stays with the view where you drew it. | Select a markup to see its chip. Read the text. Click change to pick another attachment. | Report: Appendix J, Coordination tools |
| Change attachment | The link opens a menu of attachments. You can use the selected elements, the surface, a 3D region, a measurement, a penetration or view-locked. | The shape moves to the new target. Undo brings the old target back. | Click change. Pick a choice. For a measurement or penetration, click it in the view. | Report: Appendix J, Coordination tools |
| Set card | The card shows a set with its picture and its counts. | Click and the view comes back with its notes. | Click a card. | Report: Appendix J, Coordination tools |
| Other models (group) | The group lists the sets made on other models. It starts closed. | Those sets stay out of the view, so an old note never sits on the wrong building. | Click the heading to open the group. Pick Open, Move to this model or Delete. | Report: Appendix J, Coordination tools |
| Open | The button shows a set of another model on this model. | The set joins the list until you load a model again. Its shapes can sit in the wrong place. | Click the button. Check where the notes land. | Report: Appendix J, Coordination tools |
| Move to this model | The button makes the set belong to the model on screen. | The set joins the list for good. Shapes whose parts are missing here lock to the screen and show a warning. | Click the button. Read the status line for the count of locked shapes. | Report: Appendix J, Coordination tools |
| Model tag | The tag says the set comes from a revised model, or from a file that names none. | A new revision can move or remove the parts that a shape holds on to. Those shapes lock to the screen. | Hover the tag to read why. Move to this model when the set belongs here. | Report: Appendix J, Coordination tools |
| Markup row | The row shows a single markup with its number, kind, status and text. | Click and the entry opens. It shows the comments. | Click a row. Edit the text. | Report: Appendix J, Coordination tools |
| Sets (heading) | The heading names the list of markup sets. | The list shows each card with a picture. | Read the cards. | Report: Appendix J, Coordination tools |
| Tools (heading) | The heading names the drawing tools. | Each one makes a different kind of mark. | Pick a tool. | Report: Appendix J, Coordination tools |
| Markups (heading) | The heading names the list of markups of the active set. | Each row has a number that matches the number on the view and in the PDF. | Click a row to edit it. | Report: Appendix J, Coordination tools |
| Status line | The line shows the last message of the Markup tool. | A short text tells you what the tool did or why it did not. | Read the line after each action. | Report: Appendix J, Coordination tools |
| Picture quality | The list sets the picture quality of the PDF in dots per inch. Screen uses the pixels of your window. | A higher number gives sharper pages and a bigger file. | Select 200 for most prints. Select 300 for fine detail. | Report: Appendix J, Coordination tools |
| Update view | The button captures the view of the set again from the current camera, cuts and look. | Click and the set opens from this angle. The marks follow your choice of the list beside it. | Move the camera. Click the button. Press Ctrl+Z to go back. | Report: Appendix J, Coordination tools |
| Shapes stay | The list sets where drawn shapes go when you update the view. They stay on the model or on the screen. | The first choice keeps each mark on the part that it covers. The second keeps its place in the window. | Select on the model for most cases. | Report: Appendix J, Coordination tools |

## Keyboard

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Keyboard* | The folder controls keyboard navigation and the shortcut tools. Keys move the camera and run actions. | These controls set how fast the keys move the picture, and open the lists of all keys. | Change a speed here. Click Shortcuts to see every key. | Report: Appendix I, Presets and keyboard |
| keyboard navigation | The switch turns the camera keys on or off. | On: the arrow keys and W A S D move the camera. Off: those keys do nothing. | Turn the switch off if you type in other tools. | Report: Appendix I, Presets and keyboard |
| orbit speed (deg/s) | The slider sets the orbit speed of the arrow keys in degrees per second. | Move the slider right and the arrow keys spin the picture faster. Move it left and they spin it slower. | Hold Ctrl for slow moves. Increase the value for fast turns. | Report: Appendix I, Presets and keyboard |
| pan speed | The slider sets the pan speed of the Shift and arrow keys as a factor. | Move the slider right and the picture slides faster when you hold the keys. | Increase the value for big models. Decrease the value for fine work. | Report: Appendix I, Presets and keyboard |
| move speed | The slider sets the speed factor of the fly keys W A S D Q E. | Drag the slider right and the camera flies faster when you hold a key. | Increase the value for large buildings. Decrease the value for small rooms. | Report: Appendix I, Presets and keyboard |
| invert vertical | The switch reverses the direction of the vertical keys. | On: the up and down arrow keys swap their direction. Off: they act in the usual way. | Turn the switch on if the up key feels wrong. | Report: Appendix I, Presets and keyboard |
| smooth moves | The switch eases jumps to a stored view, such as front or top. When it is off, the camera jumps at once. | On: the picture glides when you jump to a new angle. Off: it jumps at once. | Turn the switch off for instant views. | Report: Appendix I, Presets and keyboard |
| Shortcuts (?) | The button opens the list of all shortcuts. Press the ? key for the same action. | Click and a list of every key and its job appears. | Click the button. Type in the search box to find a key. | Report: Appendix I, Presets and keyboard |
| Edit shortcuts | The button opens the editor for shortcuts. The editor sets, adds and removes keys for each action. | Click and you can give any action a new key. Red cells warn you of a clash. | Click the button. Click a key cell. Press the new keys. | Report: Appendix I, Presets and keyboard |
| Command palette (Ctrl+Shift+K) | The button opens the command palette. The palette searches actions and settings by name. | Click and a search box lets you find any action or setting by typing a few letters. | Click the button or press Ctrl+Shift+K. Type a name. Press Enter. | Report: Appendix I, Presets and keyboard |
| Reset shortcuts | The button restores the default shortcuts. | Click and all your own key changes go away. The standard keys return. | Click the button if a changed key causes trouble. | Report: Appendix I, Presets and keyboard |

## Imaging

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Imaging* | The folder controls the imaging styles. A style draws the model as a radiograph or as an MRI slab slice. | These controls turn the building picture into a scan, like a hospital photo or a thin slice of a body. | Choose a style. Change the exposure and the contrast until the picture looks right. | Report: Appendix G, Imaging and sectioning |
| style | The list sets the imaging style. The value standard is the normal renderer. The value radiograph draws the context by material thickness. The value mri draws a grey slab slice. | Each choice redraws the whole picture. The first is the normal picture. One looks like a hospital photo of dense parts. The last shows a thin grey cut through the selected item. | Select a style. Select an object to see the bright focus. Press the M key to cycle the styles. | Report: Appendix G, Imaging and sectioning |
| palette | The list sets the palette of the imaging styles. A palette sets the ground, the tone of the material and the glow. | Each choice changes the colours of the scan. One has a dark ground with bright parts. Another has a light ground. | Select classic for a dark ground. Select negative for a light ground. Select fluoro for a green screen look. | Report: Appendix G, Imaging and sectioning |
| auto exposure | The switch sets the exposure by itself. The viewer measures the thickness of the context and fits the brightness to the model. | On: tall or thick buildings stay readable, because the picture adapts to how much material each view crosses. Off: the brightness stays fixed. | Leave the switch on for most models. Turn it off to set the brightness only with the exposure slider. | Report: Appendix G, Imaging and sectioning |
| exposure | The slider sets the exposure. It scales the accumulated thickness before the attenuation curve. With the automatic exposure on, it multiplies the automatic value. | Move the slider right and the whole scan gets brighter. Move it left and it gets darker. | Increase the value for thin buildings. Decrease the value for dense models. | Report: Appendix G, Imaging and sectioning |
| contrast | The slider sets the steepness of the attenuation curve. | Move the slider right and thick and thin parts differ more. Move it left and the scan looks flat. | Increase the value to separate dense parts. Decrease the value for a soft picture. | Report: Appendix G, Imaging and sectioning |
| bone glow | The slider sets the strength of the glow around the focus. The focus draws bright in both styles. | Move the slider right and the selected item shines more. At 0 it has no halo. | Increase the value to find the focus quickly. Decrease the value for a plain look. | Report: Appendix G, Imaging and sectioning |
| tissue edges | The switch draws the edge lines of the context in the imaging styles. | On: the outlines of walls and slabs show clearly in the grey picture. Off: they melt into the grey. | Turn the switch on to read the shape of the context. Turn it off for a smooth scan look. | Report: Appendix G, Imaging and sectioning |

## MRI slice

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: MRI slice* | The folder controls the MRI slab slice. The slab draws grey and crisp. The surroundings draw faint. | These controls pick a thin grey cut through the selected item and fade the rest. The cut can move by itself. | Choose the axis and the thickness. Move the position. Turn the scan on to sweep the slab. | Report: Appendix G, Imaging and sectioning |
| axis | The list sets the axis across which the slab slice moves. The value camera uses the line of sight. | Choose another entry and the grey cut turns to face another side of the building. | Select camera to slice along your line of sight. Select x, y or z for a fixed direction. | Report: Appendix G, Imaging and sectioning |
| thickness (m) | The slider sets the thickness of the slab slice in metres. | Move the slider right and the grey cut gets thicker and shows more of the building. Move it left and the cut gets thin. | Increase the value to show more material. Decrease the value for a crisp slice. | Report: Appendix G, Imaging and sectioning |
| position | The slider sets the position of the slab slice along the axis. The range is 0 to 1 across the focus. | Move the slider and the grey cut slides through the selected item from one end to the other. | Move the value to look at each part of the focus. | Report: Appendix G, Imaging and sectioning |
| scan | The switch moves the slab slice along the axis by itself. When it is off, the slab stays at the chosen position. | On: the grey cut travels through the building on its own, like a hospital machine. Off: it stays where you put it. | Turn the switch on to review the whole focus. Turn it off to stop at a single position. | Report: Appendix G, Imaging and sectioning |
| scan speed | The slider sets the speed of the moving slab slice, as a fraction of the sweep per second. | Move the slider right and the cut travels faster. Move it left and it travels slower. | Decrease the value to study details. Increase the value for a quick pass. | Report: Appendix G, Imaging and sectioning |

## Section

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Section* | The folder controls the section box and the section plane. Both clip every pass per pixel and draw flat hatched caps. | These controls cut the building open with a block of space or a flat cut. Then you see the inside. | Turn the box or the plane on. Fit the box to the selection. Drag the handles to adjust it. | Report: Appendix G, Imaging and sectioning |
| box | The switch turns the section box on or off. The box clips every pass per pixel and draws flat hatched caps. Press the C key for the same action. | On: everything outside a block of space is cut away and the inside shows as a clean slice. Off: the whole building returns. | Click Fit box to selection first. Turn the switch on. Drag the handles to resize the box. | Report: Appendix G, Imaging and sectioning |
| Fit box to selection | The button sizes the section box to the bounds of the selected objects plus the margin. It also turns the box on. | Click and the cut block shrinks to wrap the picked parts with a little room around them. | Select objects first. Click the button. Press Shift+C for the same action. | Report: Appendix G, Imaging and sectioning |
| Fit box to model | The button sizes the section box to the bounds of the whole model plus the margin. It also turns the box on. | Click and the cut block grows to wrap the whole building. | Click the button to start from the full model. Drag the handles to cut in. | Report: Appendix G, Imaging and sectioning |
| margin (m) | The slider sets the extra space in metres that a fit adds on all sides of the bounds. | Move the slider right and the cut block gets roomier around the parts. At 0 it hugs them. | Increase the value to keep a margin of context. Click a fit button to apply the change. | Report: Appendix G, Imaging and sectioning |
| plane | The switch turns the section plane on or off. The plane clips 1 side of the model. Press Alt+C for the same action. | On: everything on one side of a flat cut disappears. Off: the whole building returns. | Choose the axis. Turn the switch on. Move the offset. | Report: Appendix G, Imaging and sectioning |
| axis | The list sets the axis across which the section plane stands. The choices are x, y, z and camera. | Choose another entry and the flat cut turns to face another side of the building. | Select y for a plan cut. Select x or z for an elevation. Select camera to cut across your line of sight. | Report: Appendix G, Imaging and sectioning |
| offset (m) | The slider moves the section plane along the axis, in metres from the fitted centre. | Move the slider and the flat cut slides through the building. More of the building disappears or returns. | Move the value until the plane shows the part that you need. | Report: Appendix G, Imaging and sectioning |
| flip | The switch reverses the side of the section plane that stays visible. | On: the other half of the building stays. Off: the first half stays. | Turn the switch on to look at the opposite side of the cut. | Report: Appendix G, Imaging and sectioning |
| caps | The switch draws flat hatched caps where the section box or the section plane cuts a solid. | On: cut solids show a flat hatched face, like an architect drawing. Off: you look into the hollow parts. | Turn the switch on for a clear section. Turn it off to see the inside of the shells. | Report: Appendix G, Imaging and sectioning |
| cap colour | The colour picker sets the colour of the hatched caps. | Pick a shade and the flat faces on the cut change to it. | Choose a colour that stands out from your model colours. | Report: Appendix G, Imaging and sectioning |
| show handles | The switch shows the box outline and the handles that you drag to move the box faces. | On: small round grips appear that you can drag. Off: the grips go away and the cut stays fixed. | Turn the switch off for screenshots. | Report: Appendix G, Imaging and sectioning |
| Clear section | The button turns off the section box and the section plane. | Click and every cut goes away and the whole building returns. | Click the button to start again. | Report: Appendix G, Imaging and sectioning |

## Gizmo

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Gizmo* | The folder controls the view cube and the section strip in the lower right corner of the 3D view. | Untick the box and the little block with its buttons leaves the picture. Tick it and it comes back. | Press the V key to show or hide the tools. Click the minus button to fold them into 1 button. | Report: Appendix I, Presets and keyboard |
| show | The switch shows or hides the view cube and the section strip. The V key does the same. | On: a small block with labelled sides sits in the lower right corner. Off: the corner stays empty. | Turn the switch off for clean screenshots. Press V to turn it on again. | Report: Appendix I, Presets and keyboard |
| View cube | The cube turns with the camera. A click on a face, an edge or a corner moves the camera to look from that side. | Click the side marked Top and the camera swings above the building. Drag the block to spin the picture. | Click a face for a straight look and an edge or a corner for an angled look. Drag to orbit. Press Alt+7 for top, Alt+1 for front and Alt+3 for right. | Report: Appendix I, Presets and keyboard |
| Roll clockwise | The button turns the camera 90 degrees about the line of sight. The picture turns clockwise on the screen. | Click and the whole picture tips a quarter turn to the right, like a page that you rotate. | Click the button to read a plan from another side. Click a face of the cube to undo the tilt. | Report: Appendix I, Presets and keyboard |
| Roll counter-clockwise | The button turns the camera 90 degrees about the line of sight. The picture turns counter-clockwise on the screen. | Click and the whole picture tips a quarter turn to the left, like a page that you rotate. | Click the button to read a plan from another side. Click a face of the cube to undo the tilt. | Report: Appendix I, Presets and keyboard |
| Turn left | The button moves the camera 90 degrees around the vertical axis through the target, to the left. | Click and you walk a quarter of the way around the building, so you see the next side. | Click the button 4 times to go once around the model. | Report: Appendix I, Presets and keyboard |
| Turn right | The button moves the camera 90 degrees around the vertical axis through the target, to the right. | Click and you walk a quarter of the way around the building the other way, to the next side. | Click the button 4 times to go once around the model. | Report: Appendix I, Presets and keyboard |
| Home | The button frames the whole model from the default corner. The camera moves there in a smooth arc. | Click and the full building comes back into the picture, seen from above at an angle. | Click the button when you lose your way. Press the Home key to frame all without the arc. | Report: Appendix I, Presets and keyboard |
| Projection | The button switches between the perspective camera and an orthographic approximation with a 2 degree field of view. | On: lines that run in parallel stay parallel, like on a drawing board. Off: distant parts look smaller. | Click the button for plans and elevations. Press Alt+5 or Numpad 5 for the same action. | Report: Appendix I, Presets and keyboard |
| Collapse | The button folds the view cube and the section strip into 1 small button. | Click and the corner tools shrink to a single square, so you see more of the building. | Click the small square to open the tools again. Press V to hide them completely. | Report: Appendix I, Presets and keyboard |
| Open gizmo | The button opens the view cube and the section strip again. | Click and the labelled block and its buttons come back in the corner. | Click the button to reach the cube and the cut tools. | Report: Appendix I, Presets and keyboard |
| Select mode | The button sets the arrow mode. A click picks 1 element and a drag draws a box. A box dragged to the right picks what lies inside it. A box dragged to the left picks all that it touches. | Drag over the building and a frame appears. Parts inside the frame light up as your pick. | Press R for this mode. Hold Shift to add to your pick. Hold Ctrl to toggle. Press Esc to cancel a box. | Report: Appendix I, Presets and keyboard |
| Move mode | The button sets the hand mode. A drag moves the camera and a click still picks 1 element. This is the default. | Drag over the picture and the building turns under your hand. Click a part and it lights up. | Press G for this mode. Drag to orbit. Drag with Shift or the right button to pan. Roll the wheel to zoom. | Report: Appendix I, Presets and keyboard |
| Undo | The button takes back the last camera move, pick or setting change. The tip names the step. | Click and the picture goes back to how it looked before your last change. | Click the button after a wrong zoom or a wrong pick. Press Ctrl+Z for the same step. | Report: Appendix I, Presets and keyboard |
| Redo | The button brings back the step that the last undo took away. The tip names the step. | Click and the change that you just took back returns to the picture. | Click the button after an undo that went too far. Press Ctrl+Shift+Z or Ctrl+Y for the same step. | Report: Appendix I, Presets and keyboard |
| Plane X | The button adds a section plane square to the x axis through the centre of the selection or the model. | Click and the building splits from side to side, so you look inside it. Click again and the cut goes away. | Click the button for a cut across the model. Drag the arrow on the model to move the cut. | Report: Appendix G, Imaging and sectioning |
| Plane Y | The button adds a horizontal section plane through the centre of the selection or the model. The cut is a plan. | Click and the upper part of the building goes away, so you look down into the rooms from above. | Select a storey or a room first. Press Alt+C to turn the cut on or off. | Report: Appendix G, Imaging and sectioning |
| Plane Z | The button adds a section plane square to the z axis through the centre of the selection or the model. | Click and the building splits from front to back, so you look inside it. Click again and the cut goes away. | Click the button for a cut along the length. Drag a ring on the model to tilt the cut. | Report: Appendix G, Imaging and sectioning |
| Section box | The button fits a section box to the selection, else to the model, and turns it on. | Click and only the chosen parts and a little space around them stay in the picture. | Select the parts first. Drag the round handles on the model to resize. Press Shift+C for the same fit and C to toggle. | Report: Appendix G, Imaging and sectioning |
| Flip plane | The button keeps the other side of the section plane. | Click and the half that you saw goes away and the hidden half comes back. | Click the button to look at the cut from the other side. | Report: Appendix G, Imaging and sectioning |
| Caps | The switch draws flat hatched caps where a cut goes through a closed solid. | On: cut walls look solid with a striped face. Off: you look into hollow shells. | Turn the switch off to see inside thin parts. Turn it on for a clear drawing. | Report: Appendix G, Imaging and sectioning |
| Clear section | The button turns off the section box and the section plane and removes every clip plane. | Click and every cut goes away and the whole building returns. | Click the button to start again. | Report: Appendix G, Imaging and sectioning |

## Point cloud

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Point cloud* | The folder controls point clouds. The viewer loads PLY, PCD, XYZ, PTS and LAS files and aligns them to the model. | These controls show scan dots from a site survey next to the building and check them against it. | Click Open point cloud. Align the cloud to the model. Click Compute deviation to see the errors. | Report: Appendix K, Packaging, point clouds and large models |
| Open point cloud | The button opens a file picker for a point cloud file. The viewer reads PLY, PCD, XYZ, PTS and LAS files in the browser. | Click and pick a scan file from your computer. Its dots appear next to the building. | Click the button. Choose a file. You can also drop the file on the viewer. | Report: Appendix K, Packaging, point clouds and large models |
| visible | The switch shows or hides the point cloud. | On: the scan dots show. Off: they disappear but stay loaded. | Turn the switch off to compare the building alone. | Report: Appendix K, Packaging, point clouds and large models |
| point size | The slider sets the size of each point in pixels. | Move the slider right and the dots get bigger and fill the gaps. Move it left and they get finer. | Increase the value for sparse scans. Decrease the value for dense scans. | Report: Appendix K, Packaging, point clouds and large models |
| colour by | The list sets how the points get colour: rgb, intensity, height, classification or deviation from the model surface. | Each choice paints the dots in a new way. The ways are true shade, brightness, height, surface kind and error. | Select rgb for the scanner colours. Select deviation after you click Compute deviation. | Report: Appendix K, Packaging, point clouds and large models |
| point budget | The slider sets the largest number of points that the viewer keeps. A larger cloud is decimated to this number. | Move the slider right and the scan looks denser but may update slower. Move it left and the picture stays quick but thin. | Decrease the value if the frame rate falls. Increase the value for detail. The new value applies when you release the slider. | Report: Appendix K, Packaging, point clouds and large models |
| coordinates | The list sets the coordinate system in which the viewer reads the points. The value project uses the IFC project frame. The value viewer uses the viewer frame. | Choose another entry and the scan can jump to a different place next to the building. | Select project for a scan in site coordinates. Select viewer for a scan already in the viewer frame. | Report: Appendix K, Packaging, point clouds and large models |
| Auto-align to model | The button matches the bounds centres of the cloud and the model. It then tries 0, 90, 180 and 270 degrees about the vertical axis. | Click and the scan slides and turns to sit on the building. | Click the button after you load a scan. Fine tune with the offsets and the rotation. | Report: Appendix K, Packaging, point clouds and large models |
| offset x | The field moves the point cloud along the x axis of the viewer, in metres. | Type a number and the whole scan shifts sideways through the building. | Enter a value in metres. Use it to fine tune the fit. | Report: Appendix K, Packaging, point clouds and large models |
| offset y | The field moves the point cloud along the y axis of the viewer, in metres. The y axis points up. | Type a number and the whole scan rises or sinks next to the building. | Enter a value in metres. Use it to match the level of the scan. | Report: Appendix K, Packaging, point clouds and large models |
| offset z | The field moves the point cloud along the z axis of the viewer, in metres. | Type a number and the whole scan shifts forward or back through the building. | Enter a value in metres. Use it to fine tune the fit. | Report: Appendix K, Packaging, point clouds and large models |
| rotation (deg) | The slider turns the point cloud about the vertical axis, in degrees. | Move the slider and the scan turns in place. Use it when the scan sits at a wrong angle. | Click Auto-align to model first. Then change the value in small steps. | Report: Appendix K, Packaging, point clouds and large models |
| keep vertical | The switch limits 3-point alignment and ICP to a turn about the vertical axis and a move. The cloud stays upright. | On: the scan only slides and spins flat, so it never tips over. Off: it may also tilt. | Keep the switch on for phone and tripod scans. Turn it off only for a scan that leans. | Report: Appendix K, Packaging, point clouds and large models |
| allow scale | The switch lets 3-point alignment also change the size of the cloud by 1 uniform factor. The default is off. | On: the scan may grow or shrink to fit the picked spots. Off: its size stays true. | Leave the switch off for phone and laser scans in metres. Turn it on for a model of unknown size. | Report: Appendix K, Packaging, point clouds and large models |
| align within | The list sets the part of the cloud that 3-point alignment and ICP use. The value whole cloud uses all points. The value section box uses the points in the active section box. The value selection uses the bounds of the selected elements plus 0.5 m. | Pick a room and the scan fits that room closely, even when the rest of a long scan bends. | Put a section box around 1 room, or select its walls and slab. Choose the value. Pick pairs in that room and click Refine. Do the same for each room. | Report: Appendix K, Packaging, point clouds and large models |
| Align by 3 points | The button starts a guided mode. Click a point on the cloud and then the same point on the model, 3 times or more. | You click matching spots on the scan and on the building, and the scan jumps into place. | Click the button. Pick corners that are far apart. Press Escape to undo a pending pick, then to cancel. | Report: Appendix K, Packaging, point clouds and large models |
| Refine (ICP) | The button fits the cloud to the model surfaces with point-to-plane ICP. It matches each point only with a surface that faces the same way. It reverts if the fit gets worse. | Click and the scan settles onto the walls and slabs to the last millimetre or two. | Align roughly first with Auto-align to model or Align by 3 points. Click the button. Read the status line and the grid of 9 plan regions below the button. A red cell shows where the scan bends. | Report: Appendix K, Packaging, point clouds and large models |
| Undo alignment | The button restores the transform from before the last alignment step: Auto-align, 3-point alignment, ICP or reset. | Click and the scan jumps back to where it sat before your last fix. | Click the button after a step that made the fit worse. | Report: Appendix K, Packaging, point clouds and large models |
| Reset alignment | The button sets the offsets and the rotation to 0 and removes the registration matrix. | Click and the scan returns to the spot and angle it had in the file. | Click the button to start the alignment again from the file coordinates. | Report: Appendix K, Packaging, point clouds and large models |
| Compute deviation | The button measures the deviation of each point from the model surface. Green is within the tolerance, amber up to twice, red beyond. | Click and the dots turn green where the building matches. They turn amber where it is a little off and red where it is way off. | Align the cloud first. Click the button. Wait for the result line. | Report: Appendix K, Packaging, point clouds and large models |
| tolerance (m) | The field sets the tolerance in metres. A point within it is green. A point up to twice it is amber. A point beyond is red. | Type a larger number and more dots count as good. Type a smaller number and the check gets strict. | Set the tolerance of your project. Click Compute deviation again after a change. | Report: Appendix K, Packaging, point clouds and large models |
| deviation scope | The list sets which model elements the deviation test compares the points with. The value all elements uses the whole model. The value focus only uses the focus set. | Choose the first and the scan gets checked against the whole building. Choose the second and just against the picked parts, which runs faster. | Select all elements for a full check. Select focus only to check 1 system. | Report: Appendix K, Packaging, point clouds and large models |
| Remove point cloud | The button removes the point cloud from the viewer and frees its memory. | Click and the scan dots disappear. The building stays. | Click the button before you load another scan. | Report: Appendix K, Packaging, point clouds and large models |
| Point cloud status | The read-only field shows the file name, the point count and the state of the last step. | A short text tells you what you have loaded and how the work is going. | Read the line after each step. | Report: Appendix K, Packaging, point clouds and large models |

## WebXR

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: WebXR* | The folder controls the experimental WebXR mode. It starts a virtual reality or an augmented reality session on a headset or a phone. | These controls put you inside the building with a headset, or place a small copy on a real table. | Click Enter VR or Enter AR. The buttons show only when the device supports the mode. | Report: Appendix M, WebXR |
| Enter VR | The button starts an immersive virtual reality session at real scale. The camera starts at the position of the orbit camera. | Click and the building surrounds you in the headset, at its real size, from the spot where you stood. | Put on the headset. Click the button. Point a controller at an object and pull the trigger to select it. Use the thumbsticks to turn and walk. | Report: Appendix M, WebXR |
| Enter AR | The button starts an augmented reality session. A ring on a real surface shows where the viewer places the model. | Click and the building appears in your room, seen through the camera of your phone or headset. | Point the device at a table or at the floor. Tap to place the model. Choose the size first. | Report: Appendix M, WebXR |
| AR scale | The list sets the size of the model in augmented reality. The value 1:1 is real size. The value tabletop 1:50 shrinks the model 50 times. | Choose 1:1 and the building stands life size around you. Choose the other entry and it sits on your table like a small model. | Select 1:1 to walk through the building. Select tabletop 1:50 to look at it from above. | Report: Appendix M, WebXR |
| XR status | The read-only text shows the state of the WebXR session and the drawing steps that the session leaves out. | A short line tells you if the device is ready and which looks stay off inside the headset. | Read the line if the picture in the headset looks plainer than on the screen. | Report: Appendix M, WebXR |
| pointer rays | The switch shows a line from each controller or hand. The line ends where it meets an object. | On: a coloured line shows where you aim, and it turns yellow on an object. Off: you aim without a line. | Turn the switch on to see where you aim. Turn it off for a clear view of the model. | Report: Appendix M, WebXR |
| Enter field AR | The button starts an augmented reality session at real size for use on the building site. Point pairs line up the model with the real building. | Tap and the pipes and ducts appear in place behind the real walls and ceilings around you. | Pick 2 or more model points first. Click the button on site. Tap the same points in the room, in the same order. | Report: Appendix M, WebXR |
| field look | The list sets how much of the model the field session shows. X-ray shows only the services, ghosted adds faint structure, full shows everything. | Pick the first entry to see only pipes and ducts. Pick the middle entry for faint walls too. Pick the last for the whole building. | Select ghosted on site. Select x-ray when walls hide too much. Select full to check the registration against the real walls. | Report: Appendix M, WebXR |
| Pick model points | The button starts and stops point picking in the normal view. Each click on the model adds 1 point for the field registration. | Click a few corners on the screen now, then tap the same spots on site to line up the building. | Click the button. Click 2 or more wall corners, column centres or marks far apart. Click the button again to stop. | Report: Appendix M, WebXR |
| Clear model points | The button removes the model points picked for the field registration. | Click to forget the corners you chose, so you can choose new ones. | Click the button before you pick a new set of points. | Report: Appendix M, WebXR |
| cut radius (m) | The slider sets the half size of the section box around you in a field session, in metres. The value 0 switches it off. | A small value hides what lies more than a few metres away, so the view stays clear. | Set 4 to 8 metres indoors. Set 0 to see the whole storey. | Report: Appendix M, WebXR |
| storey cut | The switch cuts the model at the ceiling of the storey where you stand and 1 m below its floor. | On: the levels above and below you vanish, so only the services around your room remain. | Turn the switch on in a building with several levels. Turn it off to look up a shaft. | Report: Appendix M, WebXR |
| restore saved site | The switch makes a field session start from the newest saved registration of this model. | On: the building lines up again by itself on a headset with anchors, or after 2 taps on a phone. | Turn the switch on when you come back to the same building. Turn it off to register from scratch. | Report: Appendix M, WebXR |
| snapshots to BCF | The switch turns each field snapshot into a BCF topic when the session ends. | On: every picture you take on site becomes an issue with your position, ready to send. | Turn the switch on to report site issues. Turn it off to keep the pictures in this page only. | Report: Appendix M, WebXR |
| Export site | The button saves the registration of this model on site as a file. | Click to keep the alignment as a file that a colleague or another device can load. | Click the button after a good registration. Send the file to the next person on site. | Report: Appendix M, WebXR |
| Import site | The button loads a registration file. The next field session starts from it. | Click to reuse an alignment that someone made earlier on the same building. | Click the button and choose the file. Then start the field session. | Report: Appendix M, WebXR |
| Download notes | The button saves the snapshots of the last field session as a file, with the position of each. | Click to keep the pictures from site with the place where you stood for each one. | Click the button after the session. Attach the file to your report. | Report: Appendix M, WebXR |
| Open in AR Quick Look | The button exports the model as you see it to a USDZ file. AR Quick Look on iPhone and iPad opens it. | Tap and the building stands on a table or the ground in front of you. It does not match the site. | Tap the button on an iPhone or iPad. Tap a surface to place the model. | Report: Appendix M, WebXR |
| Download USDZ | The button exports the model as you see it to a USDZ file for AR Quick Look. | Click to get a file that an iPhone or iPad shows on a table in front of you. | Click the button. Open the file on an iPhone or iPad. | Report: Appendix M, WebXR |
| Share link as QR | The button shows a code with the address of this view. A phone camera opens it. | Point a phone at the square and the same view opens there, ready for the site. | Click the button. Scan the code with the phone or headset that goes to site. | Report: Appendix M, WebXR |

## Tool strip

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Tool strip* | The strip holds 1 button for each tool of the action panel. A button opens the drawer of its tool or switches the tool. | This column of icons holds the extra helpers. Click an icon to open its panel or to switch the helper on. | Click a button to open its drawer. Press the T key to show or hide the strip. | Report: Onboarding checklist |
| Presets | The button opens the drawer of the Presets tool. The drawer lists the built-in presets and your own presets. | Click to see ready-made looks for the whole picture. One click on a card switches to that look. | Click the button to open the drawer. Press a key from 1 to 9 to apply a preset at once. | Report: Appendix I, Presets and keyboard |
| Open model | The button opens the file picker for an IFC or glb file. The tool has no drawer. | Click and a window asks you for a building file from your computer. | Click the button. Choose a file. You can also drop files on the viewer. | Report: Appendix K, Packaging, point clouds and large models |
| X-ray | The button turns the x-ray on or off. The tool has no drawer. The button shows blue while x-ray is on. | Click and the walls and slabs in the way fade, or they turn solid again. | Click the button or press the X key. | Report: Purpose |
| View modes | The button opens the drawer of the View modes tool. The drawer holds the main controls of behind only and peelback. | Click to open quick controls that cut holes in what hides the selected item. | Select an object. Click the button. Turn a cut on. | Report: Appendix F, View modes |
| Measure | The button opens the drawer of the Measure tool. Clicks on the canvas then measure distances. | Click to turn the mouse into a ruler. Click on the building to read a length. | Click the button. Click 2 points on the model. | Report: Appendix J, Coordination tools |
| Markup | The button opens the Markup drawer. The key K does the same. | The drawer lets you draw clouds, notes, highlights and shapes on a saved view. | Click the button or press K. | Report: Appendix J, Coordination tools |
| BCF | The button opens the drawer of the BCF tool. The drawer opens, reviews, creates and exports BCF topics. | Click to open the issue list. You can read, add and share notes tied to views of the building. | Click the button. Click Open BCF. Click a topic to review it. | Report: Appendix J, Coordination tools |
| Clearance | The button opens the drawer of the Clearance tool. The button shows blue while the colouring is on. | Click to open the closeness check. It paints parts red, amber or blue by their distance to the selected item. | Select an object. Click the button. Turn the colouring on. | Report: Appendix J, Coordination tools |
| Penetrations | The button opens the drawer of the Penetrations tool. The drawer holds the penetration schedule. | Click to open the list of places where pipes and ducts go through slabs and walls. | Click the button. Click Analyse. Click a row to fly to the crossing. | Report: Appendix J, Coordination tools |
| Large model | The button opens the drawer of the Large model tool. The drawer shows the size, the buffers and the stage timings of the last model. | Click to see how big the building is and which load step took the longest. | Open a file first. Click the button. Read the figures. | Report: Appendix K, Packaging, point clouds and large models |
| Cleanup | The button opens the drawer of the Cleanup tool. The drawer finds and hides floating or tiny debris. | Click to open helpers that find and hide stray bits of the building. | Click the button. Turn rules on. Click Preview. | Report: Appendix H, Model cleanup |
| Imaging | The button opens the drawer of the Imaging tool. The button shows blue while a style other than standard is on. The M key cycles the styles. | Click to open the scan looks that turn the picture into a hospital style photo or slice. | Select an object. Click the button. Choose a style. | Report: Appendix G, Imaging and sectioning |
| Section | The button opens the drawer of the Section tool. The button shows blue while the box or the plane is on. | Click to open helpers that cut the building open with a block or a flat cut. | Click the button. Click Fit to selection. Drag the handles. | Report: Appendix G, Imaging and sectioning |
| Scan | The button opens the drawer of the point cloud tool. The drawer opens a scan and checks it against the model. | Click to open helpers that bring in dots from a site survey and check them against the building. | Click the button. Click Open point cloud. Click Compute deviation. | Report: Appendix K, Packaging, point clouds and large models |
| WebXR | The button opens the drawer of the WebXR tool. The button shows blue while a session runs. It shows only on a device that supports virtual or augmented reality, or AR Quick Look. | Click to open the buttons that start a session on a headset or a phone. | Click the button. Click Enter VR or Enter AR. | Report: Appendix M, WebXR |
| Classify | The button opens the drawer of the Classify tool. The tool labels elements by discipline, sub-discipline and MasterFormat division. | Click to open the panel that tags each part with its trade. | Click the button. Choose a provider. Click Classify selection. | Report: Limitations and extensions, classification |

## Tool drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Tool drawer* | The drawer shows the settings and the results of the open tool. Only 1 drawer is open at a time. | This panel slides out next to the icons and shows the controls of the helper you chose. | Drag the right edge to change the width. Press Escape to close the drawer. | Report: Onboarding checklist |
| Close button | The button closes the drawer. The tool keeps its settings. Press Escape for the same action. | Click and the side panel slides away and gives the picture more room. | Click the button when you finish with the tool. | Report: Onboarding checklist |
| Resize edge | The edge changes the width of the drawer when you drag it. The viewer keeps the width for later drawers. | Drag it and the side panel gets wider or narrower. A wide panel shows long tables better. | Drag the edge left or right. | Report: Onboarding checklist |

## BCF topic dialog

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: BCF topic dialog* | The dialog collects the title, type, status, priority, labels and assignee of a new BCF topic. | This window asks a few short questions and then saves a note that remembers what you see now. | Fill in the title. Click Create topic to store the topic with a snapshot. | Report: Appendix J, Coordination tools |
| Field | The field holds a detail of the new topic, such as the title, description, type, status or priority. | Type a short text or pick from the list. These details travel with the issue note. | Fill in the title at least. | Report: Appendix J, Coordination tools |
| Create topic | The button stores the topic with a snapshot and a viewpoint of the current camera. | Click and the note joins the list, with a small picture of what you see now. | Fill in the title. Click the button. | Report: Appendix J, Coordination tools |
| Cancel | The button closes the dialog and stores nothing. | Click and the window goes away. No note gets made. | Click the button to stop. | Report: Appendix J, Coordination tools |

## Command palette

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Command palette* | The palette is a search list of every action and setting. Press Ctrl+Shift+K to open it. | This search box finds any action or setting by name, so you do not need to remember keys. | Type a few letters. Press Enter to run the chosen row. Press Escape to close the list. | Report: Appendix I, Presets and keyboard |
| Search box | The text box filters the list of actions and settings while you type. | Type a few letters and the list shrinks to the actions that match. | Type a word. Press the Down key to choose a row. Press Enter to run it. | Report: Appendix I, Presets and keyboard |
| Result row | The row names an action or setting with its path and keys. A click runs the action. | Click an item and the viewer does the job at once, with no hunt through panels. | Click the row or press Enter on it. | Report: Appendix I, Presets and keyboard |

## Shortcut sheet

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Shortcut sheet* | The sheet lists every shortcut by group. Press the ? key to open it. | This list shows which key does what, so you can learn the keys quickly. | Type in the search box to filter the list. Click Edit shortcuts to change a key. | Report: Appendix I, Presets and keyboard |
| Search box | The text box filters the shortcut list while you type. | Type a word and only the keys that match stay on the list. | Type the name of an action. | Report: Appendix I, Presets and keyboard |
| Edit shortcuts | The button closes the sheet and opens the shortcut editor. | Click and you can change any key to suit your own habits. | Click the button to change a key. | Report: Appendix I, Presets and keyboard |
| Close | The button closes the shortcut sheet. Escape does the same. | Click and the list goes away and you can work on the picture again. | Click the button or press Escape. | Report: Appendix I, Presets and keyboard |
| Shortcut row | The row names an action with the keys that run it. | Each entry tells you the job and the keys for it, so you can learn them. | Read the keys. Press them in the viewer. | Report: Appendix I, Presets and keyboard |

## Shortcut editor

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Shortcut editor* | The editor sets, adds and removes the keys of each action. Red cells mark keys that 2 actions share. | This window lets you give any action your own key. A red cell warns you of a clash. | Click a key cell. Press the new keys. Press Backspace to remove the key. | Report: Appendix I, Presets and keyboard |
| Filter box | The text box filters the list of actions while you type. | Type a word and only the matching actions stay on the list. | Type the name of an action. | Report: Appendix I, Presets and keyboard |
| Export JSON | The button downloads your changed shortcuts as a JSON file. | Click and your key changes go into a file that you can keep or share. | Click the button to back up your keys. | Report: Appendix I, Presets and keyboard |
| Import JSON | The button reads shortcuts from a JSON file and applies them. | Click and pick a file of keys. Your keys change to match it. | Click the button. Choose a file from a colleague. | Report: Appendix I, Presets and keyboard |
| Reset all | The button restores the default shortcuts for every action. | Click and every key change that you made goes away. | Click the button if the keys become confusing. | Report: Appendix I, Presets and keyboard |
| Close | The button closes the shortcut editor. Escape does the same. | Click and the window goes away. Your key changes stay. | Click the button or press Escape. | Report: Appendix I, Presets and keyboard |
| Reset row | The button restores the default keys of 1 action. | Click and the keys of this action go back to their standard form. | Click the button next to an action that you changed. | Report: Appendix I, Presets and keyboard |
| Key cell | The cell shows 1 key of an action. A click starts the capture of a new key. | Click it, then press the combination you want. The old one gives way to the new one. | Click the cell. Press the new keys. Press Backspace to remove the key. Press Escape to cancel. | Report: Appendix I, Presets and keyboard |
| Add key cell | The cell adds another key to an action. A click starts the capture of the key. | Click it, then press the combination you want. The action then answers to one more. | Click the cell. Press the new keys. | Report: Appendix I, Presets and keyboard |

## Presets drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Presets drawer* | The heading names the Presets drawer. The drawer lists the built-in presets and your own presets as cards. | This panel shows ready-made looks as cards. One click on a card switches the whole picture. | Click Apply on a card. Click Save current as preset to keep your own look. | Report: Appendix I, Presets and keyboard |
| Apply | The button applies the preset of its card. The model, the selection and the camera stay as they are. | Click and the picture switches to the look of this card in one step. | Click the button on a card. Read the status line for skipped settings. | Report: Appendix I, Presets and keyboard |
| Edit | The button opens the name and description of your own preset for editing. Built-in presets have no Edit button. | Click and two text boxes let you rename the look and change its note. | Click the button. Change the text. Click Save. | Report: Appendix I, Presets and keyboard |
| Delete | The button deletes your own preset. Built-in presets have no Delete button. | Click and the card disappears from the list. The look is gone for good. | Click Export first if you want a copy. Click the button to delete. | Report: Appendix I, Presets and keyboard |
| Share | The button copies a link that applies your own preset. The link holds the preset in its address. | Click and you get a link that you can send. A colleague who opens it sees your look. | Click the button. Paste the link in a message. Send it only to people that you trust. | Report: Appendix I, Presets and keyboard |
| Duplicate | The button makes a copy of the preset as your own preset. It works for built-in presets too. | Click and a new card appears that you can change. The original stays unchanged. | Click the button. Click Edit on the copy to rename it. | Report: Appendix I, Presets and keyboard |
| Save | The button stores the form. A new preset keeps the ticked sections of the current settings. An edit keeps the new name and description. | Click and your look joins your own group of looks. A name must be there first. | Type a name. Tick at least 1 section. Click the button. | Report: Appendix I, Presets and keyboard |
| Cancel | The button closes the form and stores nothing. | Click and the form goes away. Your list stays unchanged. | Click the button to stop. | Report: Appendix I, Presets and keyboard |
| Name box | The text box holds the name of the preset. | Type a short title. It shows on the card and in the list of looks. | Type a name that tells the purpose of the look. | Report: Appendix I, Presets and keyboard |
| Description box | The text box holds a short description of the preset in 1 sentence. | Type a short note. It shows under the name on the card. | Write 1 sentence that says what the look shows. | Report: Appendix I, Presets and keyboard |
| Section tick | The tick adds a group of settings to the new preset. Only ticked groups are stored. | Mark the parts of the picture that the look must change. Leave the others alone. | Tick the sections to store. Leave the rest unticked. | Report: Appendix I, Presets and keyboard |
| Preset card | The card shows 1 preset with its name, key, description and buttons. | Each panel is a ready-made look. The coloured one marks the look that is on now. | Read the description. Click Apply to use the look. | Report: Appendix I, Presets and keyboard |
| Key badge | The badge shows the number key that applies the preset. Only the first 9 presets have a key. | The small number tells you which button on the keyboard jumps to this look. | Press the key in the viewer. | Report: Appendix I, Presets and keyboard |
| Active badge | The badge marks the preset that is active. The mark clears when you change any setting afterwards. | The word tells you that the picture still matches this look. | Look for the badge to learn which look is on. | Report: Appendix I, Presets and keyboard |
| Skipped list | The text lists the settings that the preset could not apply in this build or model. | The note tells you which parts of the look did not switch on. The rest worked. | Read the list. Ignore it if the skipped parts do not matter to you. | Report: Appendix I, Presets and keyboard |
| Review (heading) | The heading names the group Review. Its presets set up the x-ray view for model checks. | These looks help you check services against the building structure. | Open a card of this group to apply it. | Report: Appendix I, Presets and keyboard |
| Cutaway (heading) | The heading names the group Cutaway. Its presets turn on the behind-only view, the peelback or the section box. | These looks cut the building open to show the selected item. | Select an object. Click Apply on a card of this group. | Report: Appendix I, Presets and keyboard |
| Imaging (heading) | The heading names the group Imaging. Its presets turn on the radiograph or the MRI style. | These looks turn the picture into a scan. | Select an object. Click Apply on a card of this group. | Report: Appendix I, Presets and keyboard |
| Presentation (heading) | The heading names the group Presentation. Its presets turn on effects for a polished picture. | These looks add glow, sky and smooth camera moves for showing the model to others. | Click Apply on a card of this group before you present. | Report: Appendix I, Presets and keyboard |
| Basic (heading) | The heading names the group Basic. Its presets return the viewer to a plain state. | These looks give you the normal building picture without any effect. | Click Apply on a card of this group to start again. | Report: Appendix I, Presets and keyboard |
| My presets (heading) | The heading names the group My presets. It lists the presets that you saved or imported. | These looks are yours. You can rename, delete and share them. | Save a preset to fill this group. | Report: Appendix I, Presets and keyboard |
| Preset group (heading) | The heading names a group of presets that an installation added. | These looks come from your team or your installation. | Open a card of this group to apply it. | Report: Appendix I, Presets and keyboard |
| Save current as preset (heading) | The heading names the form that stores the current settings as a new preset. | This form turns the picture that you set up into a look that you can reuse. | Fill in the name. Tick the sections. Click Save. | Report: Appendix I, Presets and keyboard |
| Status line | The text line shows the result of the last preset action. | A short text tells you what just happened, such as saved, applied or skipped. | Read the line after each action. | Report: Appendix I, Presets and keyboard |
| Export | The button downloads your own presets as a JSON file. The built-in presets are not in the file. | Click and your saved looks go into a file that you can keep or send to a colleague. | Save at least 1 preset first. Click the button. | Report: Appendix I, Presets and keyboard |
| Import | The button adds presets from a JSON file. Imported presets always become your own presets. | Click and pick a file of looks. They join your list. | Click the button. Choose a file from a colleague. Read the status line for problems. | Report: Appendix I, Presets and keyboard |

## View modes drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: View modes drawer* | The heading names the View modes drawer. The drawer holds the main controls of behind only and peelback. | This panel holds the quick controls that cut holes in what hides the selected item. | Select an object. Turn a cut on. Change the sliders until the view is clear. | Report: Appendix F, View modes |
| Behind only (heading) | The heading names the group of the behind-only view controls. | The controls below remove what stands between you and the selected item. | Turn the view on. Change the offset and the front treatment. | Report: Appendix F, View modes |
| Partial peelback (heading) | The heading names the group of the peelback controls. | The controls below cut a hole around the selected item and keep the rest of the walls. | Turn the peelback on. Change the radius and the feather. | Report: Appendix F, View modes |
| Behind-only view (B) | The switch turns the behind-only view on or off. It needs a selected object. Press the B key for the same action. | On: the walls and slabs in the way vanish or fade, so you see past them. Off: nothing is cut. | Select an object. Turn the switch on to see what lies past it. | Report: Appendix F, View modes |
| Peelback (P) | The switch turns the peelback on or off. It needs a selected object. Press the P key for the same action. | On: a window opens in the walls and slabs in front of the selected item. Off: nothing is cut. | Select an object. Turn the switch on to open a window to it. | Report: Appendix F, View modes |

## Measure drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Measure drawer* | The heading names the Measure drawer. Clicks on the canvas measure while the drawer is open. | This panel turns the mouse into a ruler. Dimension lines stay on the model after you close it. | Choose a mode. Click 2 points or 2 elements. Press Escape to cancel a pending point. | Report: Appendix J, Coordination tools |
| Export CSV | The button downloads the measurements as a CSV file in IFC world coordinates. | Click and your lengths go into a spreadsheet file. | Click the button after you finish measuring. | Report: Appendix J, Coordination tools |
| Measurement row | The row shows 1 measurement with its label and length. | Each item is a length that you took. The same dimension shows on the model. | Read the length. Click the cross to delete the row. | Report: Appendix J, Coordination tools |
| Delete measurement | The button deletes 1 measurement. | Click and that length disappears from the list and from the model. | Click the cross on the row. | Report: Appendix J, Coordination tools |
| Status line | The text line says what to click next, or shows the last distance. | A short text guides you through the next click and shows the last length. | Read the line while you measure. | Report: Appendix J, Coordination tools |
| Snap to vertices (12 px) | The switch moves a click to the nearest vertex of the hit triangle when the vertex lies within 12 px. | On: your click jumps to the closest corner of the surface if one lies close. Off: the click lands exactly where you point. | Turn the switch on to measure from corner to corner. Turn it off to measure at any spot. | Report: Appendix J, Coordination tools |
| Clear | The button deletes all dimension lines from the model. | Click and every dimension line disappears from the model. | Export the measurements first if you need them. Click the button to start again. | Report: Appendix J, Coordination tools |

## BCF drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: BCF drawer* | The heading names the BCF drawer. The drawer lists BCF topics and shows the detail of the chosen topic. | This panel lists issue notes and lets you open, read, add and share them. | Click Open BCF or drop a file on the page. Click a topic to read it. | Report: Appendix J, Coordination tools |
| Apply | The button applies 1 viewpoint of the topic. It moves the camera, selects, hides and colours elements and sets clip planes. | Click and the picture jumps to what the issue note shows, with the same cuts and colours. | Click the button on a viewpoint. Read the status line for skipped parts. | Report: Appendix J, Coordination tools |
| Clear | The button clears the applied viewpoint. It is on only for the viewpoint that is active. | Click and the picture returns to your own state, without the hides, colours and cuts of the note. | Click the button after you review a viewpoint. | Report: Appendix J, Coordination tools |
| Add comment | The button adds your comment to the topic. It can attach the current view as a new viewpoint. | Click and your text joins the thread of the issue note, with a picture if you ask for it. | Type a comment. Tick attach current view if needed. Click the button. | Report: Appendix J, Coordination tools |
| Status filter | The list filters the topics by status. | Pick a state and only the issue notes in that state stay on the list. | Select All statuses to see every topic. | Report: Appendix J, Coordination tools |
| Search box | The text box filters the topics by title, description, assignee, labels and comments. | Type a word and only the issue notes that hold it stay on the list. | Type part of a word. Clear the box to see every topic. | Report: Appendix J, Coordination tools |
| Topic row | The row shows 1 topic with its status, priority and counts. A click selects the topic. | Each item is an issue note. A click opens its picture, text and comments below. | Click the row to read the topic. | Report: Appendix J, Coordination tools |
| Other models (group) | The group lists the topics made on other models. It starts closed. | Those topics stay out of the view, so an old marker never sits on the wrong building. | Click the heading to open the group. Pick Open, Move to this model or Delete topic. | Report: Appendix J, Coordination tools |
| Open | The button shows a topic of another model on this model. | The topic joins the list until you load a model again. Its markers can sit in the wrong place. | Click the button. Check where the markers land. | Report: Appendix J, Coordination tools |
| Move to this model | The button makes the topic belong to the model on screen. | The topic joins the list for good. Notes whose parts are missing here lock to the screen. | Click the button. Read the status line for the count of locked notes. | Report: Appendix J, Coordination tools |
| Delete topic | The button removes a topic of another model from the session. | Click twice and it is gone. Export a file first if you need it later. | Click the button. Click again to confirm. | Report: Appendix J, Coordination tools |
| Topic status list | The list sets the status of the selected topic. | Pick a value and the issue note changes state, for example from open to closed. | Select the new status. Export the topics to share the change. | Report: Appendix J, Coordination tools |
| Snapshot | The picture shows the snapshot that the first viewpoint of the topic stores. | The small picture shows what the author saw when they made the note. | Look at the picture. Click Apply to see it live. | Report: Appendix J, Coordination tools |
| Viewpoints (heading) | The heading names the list of viewpoints of the selected topic. | The buttons below jump to the views that the author saved. | Click Apply on a viewpoint. | Report: Appendix J, Coordination tools |
| Comments (heading) | The heading names the comments of the selected topic. The number is the count. | The notes below are the talk about this issue, oldest first. | Read the comments. Add your own below. | Report: Appendix J, Coordination tools |
| Show pins | The button shows or hides the numbered markers of the topics on the model while this drawer is open. The markers follow the topic filter. With the drawer closed only the marker of the applied viewpoint shows. | Click and the numbered dots of the issue notes appear on the building or go away. | Click the button to turn the markers on or off. Click a marker to open its topic. | Report: Appendix J, Coordination tools |
| Place pin | The button starts the placement of the topic marker. The next click on the model sets the 3D point of the topic. | Click it, then click the building, and a numbered dot marks that spot for the issue note. | Click the button. Click a surface of the model. Press Esc to stop. | Report: Appendix J, Coordination tools |
| Remove pin | The button removes the marker from the selected topic. | Click and the numbered dot of this issue note goes away from the building. | Click the button. Click Place pin to set a new marker. | Report: Appendix J, Coordination tools |
| Add callout | The button starts a callout on the active viewpoint. The next click selects the target element and the anchor point. | Click it, then click a part of the building, and a text box with a line points at that part. | Type the text first. Click the button. Click an element of the model. | Report: Appendix J, Coordination tools |
| Add note | The button starts a text note on the active viewpoint. The next click sets a free 3D point for the note. | Click it, then click the building, and a yellow sticky text stays at that spot. | Type the text first. Click the button. Click the model where the note goes. | Report: Appendix J, Coordination tools |
| Add arrow | The button starts an arrow on the active viewpoint. The arrow points at the element that you click next. | Click it, then click a part of the building, and a red pointer aims at that part. | Click the button. Click an element of the model. Drag the label to move the tail. | Report: Appendix J, Coordination tools |
| Add rectangle | The button starts a rectangle on the active viewpoint. You drag on the view to draw the rectangle. | Drag a box around a problem area and the issue note marks that area in its picture. | Type the text first if you want a label. Click the button. Drag on the view. Press Esc to stop. | Report: Appendix J, Coordination tools |
| Draw freehand | The button starts a freehand line on the active viewpoint. You drag on the view to draw the line. | Circle or underline a problem area by hand and the issue note keeps the line in its picture. | Type the text first if you want a label. Click the button. Drag on the view. Press Esc to stop. | Report: Appendix J, Coordination tools |
| Link measurement | The button lists the current measurements. A click on 1 measurement copies its end points and length into a callout. | Pick a distance you took with the ruler and it stays on the issue note with its value. | Measure with the Measure tool first. Click the button. Click a row of the list. | Report: Appendix J, Coordination tools |
| Delete | The button removes 1 annotation from the viewpoint. | Click and that text box and its line go away from the picture. | Click the button on the row of the annotation. | Report: Appendix J, Coordination tools |
| Markup (heading) | The heading names the markup of the selected topic: the topic marker and the annotations of its viewpoints. | The tools below put numbered dots, text boxes and arrows on the building for this issue. | Click a button below. Click a row to see the annotation. Drag a text box to move it. | Report: Appendix J, Coordination tools |
| Comment | The box shows 1 comment with its author, date and text. | Each box is one message in the talk about the issue. | Read the comment. | Report: Appendix J, Coordination tools |
| Comment box | The text box holds the comment that you add to the topic. | Type your reply here. It joins the issue note when you click the add button. | Type a comment. Click Add comment. | Report: Appendix J, Coordination tools |
| Attach view tick | The tick attaches the current camera, selection and clip planes to your comment as a new viewpoint. | Mark it and your reply carries a picture of what you see now. | Tick the box when the comment is about the current view. | Report: Appendix J, Coordination tools |
| Status line | The text line shows what the last BCF step did, such as what applied and what it skipped. | A short text tells you what the last step did and what it had to skip. | Read the line after you open a file or apply a viewpoint. | Report: Appendix J, Coordination tools |
| New topic | The button asks for a title and details. It then stores a topic with a snapshot and a viewpoint of the current camera. | Click and fill in a short form. The app saves a note that remembers what you see now. | Frame the issue in the picture. Click the button. Fill in the form. | Report: Appendix J, Coordination tools |
| Export 2.1 | The button downloads every topic as a BCF 2.1 file. | Click and all issue notes go into one file that most programs can read. | Select this version for the widest support. | Report: Appendix J, Coordination tools |
| Export 3.0 | The button downloads every topic as a BCF 3.0 file. | Click and all issue notes go into one file in the newer layout. | Select this version when all partners read BCF 3.0. | Report: Appendix J, Coordination tools |

## Clearance drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Clearance drawer* | The heading names the Clearance drawer. The drawer sets the bands and shows the counts per band. | This panel paints nearby walls and slabs by how close they sit to the selected item. | Select an object. Turn the colouring on. Read the counts in the status line. | Report: Appendix J, Coordination tools |
| Bands (heading) | The heading names the group of the 2 band limits, tight and max range. | The sliders below set when a part counts as too close and how wide the check reaches. | Change the limits to fit your clash rules. | Report: Appendix J, Coordination tools |
| Recompute | The button recomputes the clearance for the current focus. It turns the colouring on when it is off. | Click and the colours update for the item you picked now. | Select a new object. Click the button. | Report: Appendix J, Coordination tools |
| Status line | The text line shows the number of elements in each band and the compute time. | A short text counts the red, amber and blue parts and says how long the check took. | Read the line after each change. | Report: Appendix J, Coordination tools |
| Show clearance of the context to the focus | The switch turns the clearance colouring on or off. The colouring needs a selected object. | On: walls and slabs turn red, amber or blue by how close they sit to the selected item. Off: the normal colours return. | Select an object. Turn the switch on. Read the legend at the bottom right. | Report: Appendix J, Coordination tools |

## Penetrations drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Penetrations drawer* | The heading names the Penetrations drawer. The drawer holds the penetration schedule with filters and a sortable table. | This panel lists where pipes and ducts go through slabs and walls, with a cut-out check for each. | Click Analyse. Filter the rows with the chips. Click a row to fly to the crossing. | Report: Appendix J, Coordination tools |
| Create BCF topics | The button creates 1 BCF topic for each selected row, or for each filtered row when none is selected. | Click and each crossing becomes an issue note with a picture, ready to send to the team. | Click the rows to select them. Click the button. The button is off when BCF is not available. | Report: Appendix J, Coordination tools |
| Status (heading) | The heading names the status filter. The chips below filter the rows by opening status. | The chips below let you keep only the crossings with a cut-out, without one or not known. | Click a chip to filter. Click it again to clear the filter. | Report: Appendix J, Coordination tools |
| Storey (heading) | The heading names the storey filter. The chips below filter the rows by the storey of the host. | The chips below let you look at one level of the building at a time. | Click a chip to filter. Click it again to clear the filter. | Report: Appendix J, Coordination tools |
| Host class (heading) | The heading names the host class filter. The chips below filter the rows by the class of the host. | The chips below let you look at slabs, walls or beams one kind at a time. | Click a chip to filter. Click it again to clear the filter. | Report: Appendix J, Coordination tools |
| Chip: no opening | The chip filters the rows to penetrations where the host has opening data but no opening at the place. The number is the count. | Click and the list keeps the crossings that have no cut-out. The number tells you how many there are. | Click the chip to find missing openings. Click again to clear. | Report: Appendix J, Coordination tools |
| Chip: opening | The chip filters the rows to penetrations where an opening contains the place. The number is the count. | Click and the list keeps the crossings that have a cut-out. The number tells you how many there are. | Click the chip to check the planned openings. Click again to clear. | Report: Appendix J, Coordination tools |
| Chip: unknown | The chip filters the rows to penetrations of a model with no opening data. The number is the count. | Click and the list keeps the crossings that no data can judge. The number tells you how many there are. | Click the chip to see which rows need a better source file. Click again to clear. | Report: Appendix J, Coordination tools |
| Chip: Storey | The chip filters the rows to the penetrations of 1 storey. | Click and the list keeps the crossings of that level only. | Click the chip to filter. Click again to clear. | Report: Appendix J, Coordination tools |
| Chip: Host class | The chip filters the rows to the penetrations of 1 host class. | Click and the list keeps the crossings of that kind of structure only. | Click the chip to filter. Click again to clear. | Report: Appendix J, Coordination tools |
| Column: # | The column header sorts the table by the penetration number. | Click and the rows line up by their running number. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Element | The column header sorts the table by the MEP element. | Click and the rows line up by the name of the pipe or duct. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Host | The column header sorts the table by the structural host. | Click and the rows line up by the name of the slab or wall. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Storey | The column header sorts the table by the storey of the host. | Click and the rows line up by level. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Size | The column header sorts the table by the 2 smaller extents of the MEP bounds in mm. The size is approximate for inclined runs. | Click and the rows line up from small crossings to large ones. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Thk | The column header sorts the table by the thickness of the host, which is its smallest extent in mm. | Click and the rows line up from thin walls to thick slabs. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Status | The column header sorts the table by the opening status: opening, no opening or unknown. | Click and the rows with the same cut-out result group together. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Column: Gap | The column header sorts the table by the clearance between the MEP section and the opening, in mm. A negative gap means that the opening is too small. | Click and the rows line up from the tightest fit to the loosest fit. | Click the header. Click it again to reverse the order. | Report: Appendix J, Coordination tools |
| Table row | The row shows 1 penetration. A click selects the MEP element and flies the camera to the crossing. | Click here and the picture glides to that crossing and a pulse marks it. | Click the row. Hold Ctrl or Shift to select more rows. | Report: Appendix J, Coordination tools |
| Schedule table | The table lists the filtered penetrations. It shows the first 500 rows. Export the rest. | This list tells you where each pipe or duct crosses a slab or wall, and whether a cut-out waits there. | Sort with the headers. Filter with the chips. Click a row to fly to it. | Report: Appendix J, Coordination tools |
| Status line | The text line shows the counts by opening status, the numbers of MEP elements and hosts, and the analysis time. | A short text counts the crossings with a cut-out, without one and not known. | Read the line after each analysis. | Report: Appendix J, Coordination tools |
| Analyse | The button runs the analysis. It finds where MEP elements cross structural hosts and sets the opening status of each crossing. | Click and the viewer builds a list of places where pipes and ducts go through slabs and walls. Round dots mark them on the model. | Click the button after you change the scope or the model. Open the Penetrations tool to read the list. | Report: Appendix J, Coordination tools |
| Export CSV | The button downloads the filtered rows as a CSV file. | Click and the list that you see goes into a spreadsheet file. | Click Analyse penetrations first. Filter the rows in the drawer. Click the button. | Report: Appendix J, Coordination tools |
| Markers on the model | The switch draws a coloured marker at each listed crossing. | On: coloured dots sit on the building at each crossing. Off: the dots disappear. | Turn the switch off if the dots hide your view. | Report: Appendix J, Coordination tools |

## Large model drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Large model drawer* | The heading names the Large model drawer. The drawer shows the size, the buffers and the stage timings of the last model. | This panel tells you how big the building is and which load step took the most time. | Read the figures after a load. Change edges and properties in the Open model folder. | Report: Appendix K, Packaging, point clouds and large models |
| Model (heading) | The heading names the table with the size of the model. | The table below counts the parts and triangles and shows memory use and load time. | Read the figures after a load. | Report: Appendix K, Packaging, point clouds and large models |
| Table: Model | The table lists the name and the counts of elements, triangles and vertices. It also lists buffers, BVH state and load time. | The figures tell you how heavy the building is for your computer. | Compare the figures with another file to see which file is heavy. | Report: Appendix K, Packaging, point clouds and large models |
| Stages of the last load (heading) | The heading names the table with the timing of each stage of the last file load. | The table below shows which step took the most time. | Read the times after you open an IFC file. | Report: Appendix K, Packaging, point clouds and large models |
| Table: Stages of the last load | The table lists each stage of the last file load with its time. | The times tell you which step to speed up first, for example by turning edges or properties off. | Read the longest time first. | Report: Appendix K, Packaging, point clouds and large models |

## Cleanup drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Cleanup drawer* | The heading names the Cleanup drawer. The drawer holds the rule switches and the actions of the cleanup. | This panel finds stray bits of the building and lets you hide them and bring them back. | Turn rules on. Click Preview. Click Hide to hide the matches. Click Restore to undo. | Report: Appendix H, Model cleanup |
| Rules (heading) | The heading names the group of the cleanup rules. | The switches below pick which kinds of debris the tool looks for. | Turn on the rules that you need. | Report: Appendix H, Model cleanup |
| Actions (heading) | The heading names the group of the cleanup actions. | The buttons below show, hide or bring back the debris that the rules found. | Click Preview first. Click Hide when the preview looks right. | Report: Appendix H, Model cleanup |
| Floating elements | The switch turns the floating rule on or off. | On: small loose pieces count as debris. Off: this rule finds nothing. | Turn the switch on to find pieces that hang away from the building. | Report: Appendix H, Model cleanup |
| Tiny elements | The switch turns the tiny rule on or off. | On: very small parts count as debris. Off: this rule finds nothing. | Turn the switch on to find specks and small fasteners. | Report: Appendix H, Model cleanup |
| Distant strays | The switch turns the distant strays rule on or off. | On: objects that sit way off from the building count as debris. Off: this rule finds nothing. | Turn the switch on to find markers and objects at the origin. | Report: Appendix H, Model cleanup |
| Duplicates | The switch turns the duplicate rule on or off. The lowest id stays and the others match. | On: extra copies on the same spot count as debris, and the first copy stays. Off: this rule finds nothing. | Turn the switch on to remove flicker from copies that lie on top of each other. | Report: Appendix H, Model cleanup |
| Degenerate | The switch turns the degenerate rule on or off. | On: empty or broken parts count as debris. Off: this rule finds nothing. | Turn the switch on to find parts that draw nothing useful. | Report: Appendix H, Model cleanup |
| Preview | The button tints the matches magenta. The viewer frames them when fewer than 50 elements match. | Click and the pieces that the rules found turn pink, so you can check them before you hide them. | Set the rules first. Click the button. Use Select matches when a match hides inside a wall. | Report: Appendix H, Model cleanup |
| Hide | The button hides the matches and records which ids it hid. The model file does not change. | The found pieces vanish from the picture. No part gets deleted. | Click Preview matches first. Click the button to hide the matches. | Report: Appendix H, Model cleanup |
| Restore | The button shows again only the elements that the cleanup hid. Elements that you hid yourself stay hidden. | The pieces that this tool hid come back. Parts that you hid by hand stay out of sight. | Click the button to undo the hide of the matches. | Report: Appendix H, Model cleanup |
| Status line | The read-only field shows the result of the last cleanup step. | A short text tells you how many pieces the rules found or hid. | Read the line after each step. | Report: Appendix H, Model cleanup |

## Imaging drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Imaging drawer* | The heading names the Imaging drawer. The drawer holds the imaging style, the palette and the MRI slab controls. | This panel turns the picture into a scan look and tunes how bright and how sharp it is. | Choose a style. Select an object. Change the sliders. Press the M key to cycle the styles. | Report: Appendix G, Imaging and sectioning |
| Style (heading) | The heading names the group of the imaging style controls. | The controls below pick the scan look and tune its brightness and glow. | Choose a style. Change the sliders. | Report: Appendix G, Imaging and sectioning |
| MRI slice (heading) | The heading names the group of the MRI slab slice controls. | The controls below place and move the thin grey cut. | Choose the axis. Change the position and the thickness. | Report: Appendix G, Imaging and sectioning |
| Standard view | The button sets the imaging style to standard. The normal renderer returns. | Click and the scan look goes away and the normal picture returns. | Click the button to leave the scan look. | Report: Appendix G, Imaging and sectioning |
| Status line | The text line shows the state of the imaging path or the reason why imaging is not available. | A short text tells you if the scan look works on your computer. | Read the line if the picture does not change. | Report: Appendix G, Imaging and sectioning |

## Section drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Section drawer* | The heading names the Section drawer. The drawer holds the section box, the section plane and the caps. | This panel cuts the building open with a block or a flat cut and shows the inside. | Click Fit to selection. Drag the handles on the model. Click Clear section to remove the cuts. | Report: Appendix G, Imaging and sectioning |
| Section box (heading) | The heading names the group of the section box controls. | The controls below cut the building to a block of space. | Click Fit to selection. Drag the handles on the model. | Report: Appendix G, Imaging and sectioning |
| Section plane (heading) | The heading names the group of the section plane controls. | The controls below cut the building with one flat cut. | Choose the axis. Move the offset. | Report: Appendix G, Imaging and sectioning |
| Caps (heading) | The heading names the group of the cap controls. | The controls below decide how the cut faces of solids look. | Turn the caps on. Choose their colour. | Report: Appendix G, Imaging and sectioning |
| min x | The field shows and sets 1 corner coordinate of the section box, in metres. The 6 fields follow the handles. | Type a number and that side of the cut block moves to it. The fields also follow your drags. | Type a value in metres. Press Enter. The box turns on. | Report: Appendix G, Imaging and sectioning |
| Status line | The text line shows the state of the section clipping or the reason why it is not available. | A short text tells you if the cuts work on your computer. | Read the line if the picture does not change. | Report: Appendix G, Imaging and sectioning |
| Fit to selection | The button sizes the section box to the bounds of the selected objects plus the margin. It also turns the box on. | Click and the cut block shrinks to wrap the picked parts with a little room around them. | Select objects first. Click the button. Press Shift+C for the same action. | Report: Appendix G, Imaging and sectioning |
| Fit to model | The button sizes the section box to the bounds of the whole model plus the margin. It also turns the box on. | Click and the cut block grows to wrap the whole building. | Click the button to start from the full model. Drag the handles to cut in. | Report: Appendix G, Imaging and sectioning |
| min y | The field shows and sets 1 corner coordinate of the section box, in metres. The 6 fields follow the handles. | Type a number and that side of the cut block moves to it. The fields also follow your drags. | Type a value in metres. Press Enter. The box turns on. | Report: Appendix G, Imaging and sectioning |
| min z | The field shows and sets 1 corner coordinate of the section box, in metres. The 6 fields follow the handles. | Type a number and that side of the cut block moves to it. The fields also follow your drags. | Type a value in metres. Press Enter. The box turns on. | Report: Appendix G, Imaging and sectioning |
| max x | The field shows and sets 1 corner coordinate of the section box, in metres. The 6 fields follow the handles. | Type a number and that side of the cut block moves to it. The fields also follow your drags. | Type a value in metres. Press Enter. The box turns on. | Report: Appendix G, Imaging and sectioning |
| max y | The field shows and sets 1 corner coordinate of the section box, in metres. The 6 fields follow the handles. | Type a number and that side of the cut block moves to it. The fields also follow your drags. | Type a value in metres. Press Enter. The box turns on. | Report: Appendix G, Imaging and sectioning |
| max z | The field shows and sets 1 corner coordinate of the section box, in metres. The 6 fields follow the handles. | Type a number and that side of the cut block moves to it. The fields also follow your drags. | Type a value in metres. Press Enter. The box turns on. | Report: Appendix G, Imaging and sectioning |

## Scan drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Scan drawer* | The heading names the Scan drawer. The drawer opens a point cloud, aligns it and checks it against the model. | This panel brings in dots of the real site and shows where the building differs from the plan. | Click Open point cloud. Align the cloud. Click Compute deviation. | Report: Appendix K, Packaging, point clouds and large models |
| Undo last | The button removes the last picked point of the 3-point alignment. | Click and the most recent marker disappears, so you can pick that spot again. | Click the button after a wrong click. | Report: Appendix K, Packaging, point clouds and large models |
| Cancel | The button ends the 3-point alignment without a change to the cloud. The Escape key does the same. | Click and all markers go away while the dots stay where they are. | Click the button to stop the picks. | Report: Appendix K, Packaging, point clouds and large models |
| Apply alignment | The button moves the cloud with the transform that the picked pairs give. It needs 3 pairs or more. | Click and the dots jump onto the building at the matching spots. | Check the residuals in the list. Click the button. Then click Refine for a fine fit. | Report: Appendix K, Packaging, point clouds and large models |
| Stop ICP | The button stops the running ICP. The alignment does not change. | Click and the fitting work halts while the dots stay where they are. | Click the button if the fit takes too long. | Report: Appendix K, Packaging, point clouds and large models |
| size attenuation | The switch makes points nearer to the camera look larger than points far away. | On: the dots grow as you move closer, like real objects. Off: all dots keep the same width on screen. | Turn the switch off if far dots vanish. Turn it on for a natural look. | Report: Appendix K, Packaging, point clouds and large models |
| Apply budget | The button decimates the cloud again to the point budget. The cut uses a uniform random sample. | Click and the dots get fewer or more to match the slider, which can speed up the picture. | Set the point budget. Click the button. | Report: Appendix K, Packaging, point clouds and large models |
| Deviation result | The text shows the share within tolerance, the mean and 95th percentile deviation, and the unrelated points. | These lines tell you how well the dots fit the building in plain numbers. | Read the result after Compute deviation. | Report: Appendix K, Packaging, point clouds and large models |
| Display (heading) | The heading names the group of the display controls of the point cloud. | The controls below change how the dots look. | Change the size and the colour mode. | Report: Appendix K, Packaging, point clouds and large models |
| Alignment (heading) | The heading names the group of the alignment controls of the point cloud. | The controls below move and turn the dots until they sit on the building. | Click Auto-align to model. Fine tune with the offsets. | Report: Appendix K, Packaging, point clouds and large models |
| Deviation from model (heading) | The heading names the group of the deviation controls. | The controls below check how well the dots match the building. | Set the tolerance. Click Compute deviation. | Report: Appendix K, Packaging, point clouds and large models |
| Status line | The text line shows the file name, the point count and the state of the last step. | A short text tells you what you have loaded and how the work is going. | Read the line after each step. | Report: Appendix K, Packaging, point clouds and large models |

## WebXR drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: WebXR drawer* | The heading names the WebXR drawer. The drawer holds the buttons that start and end a session. | This panel puts you inside the building with a headset, or on a real table with a phone. | Click Enter VR or Enter AR. Click Leave XR session to return to the screen. | Report: Appendix M, WebXR |
| Leave XR session | The button ends the running session. The normal picture and the orbit camera return. | Click and you come back to the screen, with the view you had before the headset. | Click the button to end the session. | Report: Appendix M, WebXR |
| Field AR on site (heading) | The heading names the field section. The section lines up the model with the real building on site. | This part puts the plan over the real rooms, so you see what lies behind walls and ceilings. | Pick model points. Click Enter field AR on site. Follow the steps on the screen. | Report: Appendix M, WebXR |
| iPhone and iPad (heading) | The heading names the section for devices without WebXR augmented reality. | Apple handsets and tablets cannot run the live overlay, so this part gives them a model to place instead. | Click Open in AR Quick Look on the device. Click Share link as QR to open this view elsewhere. | Report: Appendix M, WebXR |
| Status line | The text line shows the state of the session and the looks that the session leaves out. | A short text tells you if the headset works and what is missing from the picture there. | Read the line if the picture in the headset looks plainer than on the screen. | Report: Appendix M, WebXR |

## Classify drawer

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| *Folder: Classify drawer* | The heading names the Classify drawer. The drawer sets how the viewer labels each element by discipline and division. | This panel puts a trade and a work section on every part of the building. | Choose a provider. Click Classify selection or Classify all. Check the table. | Report: Limitations and extensions, classification |
| Provider (heading) | The heading starts the section for the decision provider. | The block below picks who answers the questions about each part. | Read the block. Choose a provider in the list. | Report: Limitations and extensions, classification |
| Schema (heading) | The heading starts the section for the code lists. | The block below shows the lists of codes that every answer must use. | Read the block. Load your own file when you have it. | Report: Limitations and extensions, classification |
| Run (heading) | The heading starts the section that runs the classification. | The block below starts and stops the work and tells you how many calls it needs. | Read the estimate. Click a button to start. | Report: Limitations and extensions, classification |
| Results (heading) | The heading starts the section for the result table. | The block below lists what each part got and lets you correct it. | Filter the table. Click a row to select the part. | Report: Limitations and extensions, classification |
| Review (heading) | The section holds the review walk and the review log. | You confirm or correct labels here, and the choices become part of a record. | Click Review walk to start. Use the log buttons to share your work. | Report: Limitations and extensions, classification |
| Review walk | The button opens a panel that visits the classified elements in a logical order. You confirm, correct or skip each element. | Your choices wait as pending changes. A commit writes them to the log, and they then count as the result. A skip is not a change. The Skipped count lets you revisit those elements. | Click the button after a run. Press Enter to confirm and N to skip. Tick Unsure, or press the question mark, when you only guess. Click Commit when you are done. | Report: Limitations and extensions, classification |
| Export review log | The button saves every commit of this model as a review log file. | You get a file that records who confirmed what and when. It holds the names of the people. | Click the button to back up your work or to hand it to a colleague. | Report: Limitations and extensions, classification |
| Import review log | The button replays the commits of a review log file for this model. | New commits join the record and become results. The tool skips commits that it holds already. It refuses a file of another model. | Click the button and choose a file that you exported from the same model. | Report: Limitations and extensions, classification |
| Calibrate on confirmed | The button fits a temperature for each question. It uses the labels that you committed in the review walk as truth. | Changes that you flag as unsure are guesses, so the fit leaves them out. The message counts the labels it uses and the unsure ones it skips. The model runs once for each kind of part. | Commit at least 8 kinds of part in the review walk first. Then click the button. | Report: Limitations and extensions, classification |
| Output (heading) | The heading starts the section for the output. | The block below shows the labels in the picture and saves them to files. | Turn on the colours. Export the table when the check is done. | Report: Limitations and extensions, classification |
| Provider | The list chooses who decides. Off uses the rules and the stored decisions only. Decision model runs a small model in the browser. Decision 3.0 d3-edge runs in the browser or on a server. Browser chat model runs a chat model on your graphics card. Jev calls a web service. Mock gives test answers. | With Off, only the clear cases get a label. With a local model or the web service, unclear cases get a label too. | Choose Decision model to stay offline with the best local choice. Choose Jev for the best answers. Choose Off to use rules only. | Report: Limitations and extensions, classification |
| Endpoint | The box holds the web address that receives the questions. A same-origin path to your own proxy works too. | It points the viewer at the service that answers. A wrong address makes every try fail with a message. | Keep the default for the vendor service. Type a path such as /api/jev to use a proxy. | Report: Limitations and extensions, classification |
| Model id | The box holds the version that the service must use. A pinned version gives repeatable answers. The word latest moves to new versions. | A fixed version name keeps the answers the same from day to day. The name latest can change them without notice. | Keep jev-1.13.0. Use typesafe-jev-1.13.0 on the DigitalOcean host. | Report: Limitations and extensions, classification |
| Requests at once | The number sets how many questions go out at the same time. | A higher number finishes sooner. A lower number is gentler to a service that limits calls. | Keep 4. Lower the number when the service says that you call too often. | Report: Limitations and extensions, classification |
| State size cap (bytes) | The number limits how much element data goes into each question. The viewer drops detail until the data fits. | A low limit makes each question cheaper but hides detail. A high limit gives the answer more to read. | Keep 4000. Raise it only when elements have many long properties. | Report: Limitations and extensions, classification |
| Timeout (ms) | The number sets how long the viewer waits for an answer, in milliseconds. | A low number gives up early on a slow service. A high number waits longer before it reports an error. | Keep 30000. Raise it for a slow connection. | Report: Limitations and extensions, classification |
| API key | The box takes the secret key of the service. The viewer keeps it in this tab and sends it only to the endpoint. | Paste the secret once. The box empties afterwards and the page only says that a secret exists. | Paste the key. Click Save key. Leave the box empty when you use a proxy. | Report: Limitations and extensions, classification |
| Remember on this device | The switch keeps the key in the local storage of the browser instead of the tab only. | On: the key stays after you close the browser. Anyone who uses the same browser can read it. Off: the key vanishes when the tab closes. | Keep it off on a shared computer. Turn it on only on your own computer. | Report: Limitations and extensions, classification |
| Save key | The button keeps the typed key. The box then empties. | The page remembers that a secret exists. You do not see it again. | Type the key in the box. Click the button. | Report: Limitations and extensions, classification |
| Forget key | The button removes the key from the tab and from the local storage. | The browser loses the secret. You must paste it again before the next call. | Click the button before you leave a shared computer. | Report: Limitations and extensions, classification |
| Browser model | The list chooses the chat model that runs in the browser. The text under the list gives the download and the memory size. | A smaller choice loads faster and needs less memory. A larger choice answers better. | Choose Qwen3 0.6B to start. Choose a larger model when answers are weak. | Report: Limitations and extensions, classification |
| Test connection | The button sends a small yes or no question to the chosen provider. It shows the answer and the model id. | You learn at once whether the address, the secret and the network work, before you start a long run. | Click the button. Read the line below it. | Report: Limitations and extensions, classification |
| Decision model | The list chooses a small zero-shot model from Hugging Face. The text under the list gives the download size of each data type. | A smaller choice loads faster and uses less memory. A larger choice labels unclear parts better. | Choose the default to start. Choose the base size when answers are weak. Choose the last entry to type any id. | Report: Limitations and extensions, classification |
| Hugging Face model id | The box holds the id of a model on Hugging Face, written as owner and name. The viewer checks the id before it downloads anything. | A wrong id gives a plain message at once. A right id downloads the files the first time and reuses them later. | Type owner/name. Press Enter. Click Test model to check it. | Report: Limitations and extensions, classification |
| Device | The list chooses where the model runs. Auto uses the graphics card when the browser supports it. WASM runs on the processor. | The graphics card gives answers much faster. The processor works everywhere but takes more seconds for each part. | Keep Auto. Choose WASM to test the slow path. Choose WebGPU to force the card. | Report: Limitations and extensions, classification |
| Data type | The list chooses how exact the stored numbers of the model are. Auto picks q8 on the processor and fp16 on the graphics card. | Smaller numbers download faster and run faster but can lose a little accuracy. Larger numbers are slower and more exact. | Keep Auto. Choose fp32 when answers look wrong. Choose q8 to save time. | Report: Limitations and extensions, classification |
| Hugging Face token | The box takes an access token for private or gated models. The viewer keeps it in this tab and sends it only to the Hugging Face address. | Paste the secret once. The box empties afterwards and the page only says that a secret exists. | Paste the token. Click Save token. Leave the box empty for public models. | Report: Limitations and extensions, classification |
| Remember token on this device | The switch keeps the token in the local storage of the browser instead of the tab only. | On: the secret stays after you close the browser. Anyone who uses the same browser can read it. Off: the secret vanishes when the tab closes. | Keep it off on a shared computer. Turn it on only on your own computer. | Report: Limitations and extensions, classification |
| Save token | The button keeps the typed token. The box then empties. | The page remembers that a secret exists. You do not see it again. | Type the token in the box. Click the button. | Report: Limitations and extensions, classification |
| Forget token | The button removes the token from the tab and from the local storage. | The browser loses the secret. You must paste it again before the next private download. | Click the button before you leave a shared computer. | Report: Limitations and extensions, classification |
| Test model | The button loads the model and runs a small question. It reports the time, the device, the data type and the size. | You learn at once whether the files download and which hardware answers, before you start a long run. | Click the button. Read the line below it. Wait for the first download. | Report: Limitations and extensions, classification |
| Clear model cache | The button deletes the downloaded model files from the cache of the browser. | The space comes back. The next run downloads the files again. | Click the button to free disk space. Click Test model to download again. | Report: Limitations and extensions, classification |
| Hugging Face endpoint | The box holds the web address that serves the model files. Use another address for a mirror or your own proxy. | A wrong address makes every download fail with a message. A mirror can still work when the main site does not answer. | Keep the default. Type the address of your mirror when the main site does not answer. | Report: Limitations and extensions, classification |
| Discipline hypothesis | The box holds the sentence that the model tests for each discipline. The braces mark where the name of the option goes. | A clearer sentence can give better answers. A wrong sentence gives worse answers. | Keep the default. Keep the braces in your text exactly once. | Report: Limitations and extensions, classification |
| Sub-discipline hypothesis | The box holds the sentence that the model tests for each sub-discipline. The braces mark where the name of the option goes. | A clearer sentence can give better answers. A wrong sentence gives worse answers. | Keep the default. Keep the braces in your text exactly once. | Report: Limitations and extensions, classification |
| Division hypothesis | The box holds the sentence that the model tests for each MasterFormat division. The braces mark where the name of the option goes. | A clearer sentence can give better answers. A wrong sentence gives worse answers. | Keep the default. Keep the braces in your text exactly once. | Report: Limitations and extensions, classification |
| Building hypothesis | The box holds the statement that tests whether a part belongs to a building. The braces mark where the text of the question goes. | A clearer statement sorts the parts better. A wrong statement mixes them up. | Keep the default. Keep the braces in your text exactly once. | Report: Limitations and extensions, classification |
| Reset hypotheses | The button restores the default sentences for all questions. | Your edits go away and the tested wording returns. | Click the button after an edit that made answers worse. | Report: Limitations and extensions, classification |
| Mode | The list chooses how the chat model works. Chat answers with a single letter. Embed scores every option by similarity. Hybrid embeds first and asks the chat model only for close calls. | Embed gives a score for every option and loads less. Chat can name a single letter only. Hybrid mixes both and needs the most memory. | Choose Chat to keep the old way. Choose Hybrid for the best local answers. | Report: Limitations and extensions, classification |
| Embedding model | The list chooses the model that turns text into numbers for the similarity score. Larger models need more memory. | A larger choice matches text better and loads slower. | Keep the small default. Choose the larger model when options look mixed up. | Report: Limitations and extensions, classification |
| Embedding temperature | The number sets how sharp the scores are after the similarity step. A low number favours the best option strongly. | A low number gives high confidence to the winner. A high number spreads confidence over many options. | Keep 0.05. Lower it when too many results need review. | Report: Limitations and extensions, classification |
| Hybrid margin | The number sets the gap between the best 2 options. Below the gap the chat model decides. | A higher number asks the chat model more often and costs more time. A lower number trusts the similarity score more. | Keep 0.15. Raise it when close calls go wrong. | Report: Limitations and extensions, classification |
| Custom model URL | The box holds the Hugging Face address of your own compiled chat model. Fill the library address too. | The viewer then uses your own files instead of the list. A wrong address makes the load fail with a message. | Leave the box empty to use the list. Fill both boxes to use your own files. | Report: Limitations and extensions, classification |
| Custom library URL | The box holds the address of the compiled WebGPU library of your chat model. The library runs as code in this page. | A trusted file works like the ones in the list. An unknown file can run harmful code. | Use a library only from a source that you trust. Fill the model address too. | Report: Limitations and extensions, classification |
| Import Throughline list | The button loads a Throughline Discipline code list from a JSON file of its entries. The list becomes the schema. | The labels switch to the codes of your company standards. Old results go away because the codes changed. | Click the button. Choose your export. Read the notes under the buttons. | Report: Limitations and extensions, classification |
| Export Throughline JSON | The button saves the results in the shape of a Throughline code list. Each part gets a discipline code. The sub-discipline and the division go in the attributes. | Your results go to the company system with codes it knows. The file lists codes that your company lacks. | Run the classification first. Click the button. Load the file into Throughline. | Report: Limitations and extensions, classification |
| Load schema file | The button loads your own list of codes from a JSON file. The file must have the schema xray-classification-schema/1. | The labels switch to your own codes and names. Old results go away because the codes changed. | Click the button. Choose your file. Read the message under the button when the file is wrong. | Report: Limitations and extensions, classification |
| Use built-in schema | The button goes back to the Throughline-aligned default list of codes. | The labels return to the default codes of the viewer. Your own list stays on disk. | Click the button to leave your own codes. | Report: Limitations and extensions, classification |
| Minimum confidence | The number sets the lowest confidence that needs no review. The schema gives the first value. | A higher number marks more parts for a second look. A lower number trusts more answers. | Keep 0.6. Raise it for a strict check. | Report: Limitations and extensions, classification |
| Write properties to the model | The switch writes each result as properties of the element, under the property set name of the schema. | On: search, queries and sums can use the labels. Off: the labels stay in the table only. | Keep it on to search by discipline. Turn it off to keep the elements clean. | Report: Limitations and extensions, classification |
| Rules and model | The list chooses how the fixed rules and the answering service work together. A certain rule can decide a part completely. Otherwise every part goes to the service. | The first choice answers clear parts at once. The service labels only the rest. The other choice sends every part out. | Keep Rules where certain. Choose the service for everything to test it on its own. | Report: Limitations and extensions, classification |
| Classify selection | The button labels the selected elements. | Only the parts that you picked get a trade, and the table fills with them. | Select elements. Click the button. | Report: Limitations and extensions, classification |
| Classify all | The button labels every element of the model. | Every part of the building gets a trade. A big building can need many calls. | Read the estimate above the button. Click the button. | Report: Limitations and extensions, classification |
| Stop | The button stops the run after the calls that are in flight. | The work ends soon and finished parts keep their labels. | Click the button to end a long run. | Report: Limitations and extensions, classification |
| Chip: Results | The chips filter the table. Low confidence shows results below the minimum. Needs review shows marked results. | The table shrinks to the parts that need your eyes. | Click a chip to filter. Click it again to remove the filter. | Report: Limitations and extensions, classification |
| Schedule table | The table lists a row for each result. The columns show the codes, the confidence, the 2 likeliest disciplines and the source. | You see what each part got and how sure the answer is. A click on a row picks the part. | Click a row to select the element. Click the pencil to correct it. | Report: Limitations and extensions, classification |
| Column: Element | The column gives the name of the element. | It tells you which part the row is about. | Read the name. Click the row to find the part. | Report: Limitations and extensions, classification |
| Column: Disc. | The column gives the discipline code, such as MEC or STR. | It shows the trade that owns the part. | Hover over the code to read its full name. | Report: Limitations and extensions, classification |
| Column: Sub | The column gives the sub-discipline code. | It narrows the trade down to a kind of work. | Hover over the code to read its full name. | Report: Limitations and extensions, classification |
| Column: Div. | The column gives the MasterFormat division number. | It shows the part of the building contract that covers the part. An empty cell means no division. | Hover over the number to read the division title. | Report: Limitations and extensions, classification |
| Column: Conf. | The column gives the lowest confidence of the answers for the row. | A low number means that the answer is unsure. Amber means that the row needs review. | Look at amber rows first. | Report: Limitations and extensions, classification |
| Column: Top 2 | The column gives the 2 most likely disciplines with their probabilities. | Two close numbers mean that the choice is hard. | Compare the 2 numbers. Correct the row when the second code is right. | Report: Limitations and extensions, classification |
| Column: Source | The column tells where the answer came from. The source is rules, cache, model or manual. | It shows whether a fixed rule, a stored decision, a language model or a person made the answer. | Hover over the cell to read the model id or the rule reason. | Report: Limitations and extensions, classification |
| Column: Edit | The column holds a pencil button for each row. | The pencil opens a small form for that part. | Click the pencil to correct a row. | Report: Limitations and extensions, classification |
| Override discipline | The list sets the discipline of an element by hand. | Your choice replaces the answer of the rules and the language model for this part. | Choose a discipline. Click Apply override. | Report: Limitations and extensions, classification |
| Override sub-discipline | The list sets the sub-discipline by hand. It offers the sub-codes of the chosen discipline. | Your choice narrows the trade down for this part only. | Choose a discipline first. Then choose a sub-discipline. | Report: Limitations and extensions, classification |
| Override division | The list sets the MasterFormat division by hand. | Your choice puts the part in a section of the building contract. | Choose a division or none. Click Apply override. | Report: Limitations and extensions, classification |
| Apply override | The button keeps your codes for the element. The source becomes manual and wins over every other source. | The part keeps your answer after every new run. | Choose the codes. Click the button. | Report: Limitations and extensions, classification |
| Remove override | The button deletes the manual result of the element. | Your correction goes away. The part waits for the next run. | Click the button to take back a correction. | Report: Limitations and extensions, classification |
| Cancel | The button closes the form without a change. | No change happens and the form disappears. | Click the button to leave the form. | Report: Limitations and extensions, classification |
| Colour by discipline | The switch tints each element by its discipline. A legend lists the colours. | Ducts, pipes and beams show in their own hues, so the trades stand out at a glance. | Turn it on after a run. Turn it off to see the model colours again. | Report: Limitations and extensions, classification |
| Select needs review | The button selects every element that is marked for review. | The uncertain parts light up in the picture, so you can look at them in turn. | Click the button. Step through the parts with the keyboard. | Report: Limitations and extensions, classification |
| Save needs-review set | The button opens the set editor with a query for the elements that need review. The set updates when you reopen it. | You get a named list of the uncertain parts in the side tab, ready to reuse. | Click the button. Confirm the name in the editor. | Report: Limitations and extensions, classification |
| Export CSV | The button saves the results as a CSV file with a row for each element. | You get a sheet that opens in a spreadsheet program, with the codes and the 2 best answers. | Click the button. Open the file in your spreadsheet program. | Report: Limitations and extensions, classification |
| Export JSON | The button saves the results and the run statistics as a JSON file. | You get a file with every probability for other programs to read. | Click the button. Read the file in your own scripts. | Report: Limitations and extensions, classification |
| Clear results | The button removes the results and the properties that the tool wrote. Manual results stay. | The labels vanish from search and from the table. Your own corrections stay. | Click the button before a new run with other settings. | Report: Limitations and extensions, classification |
| Clear cache | The button deletes the stored decisions of this model. | The next run asks the provider again for every group of similar parts. | Click the button after you change the provider. | Report: Limitations and extensions, classification |
| Pictures (heading) | The heading starts the section for the pictures of the element. A model that reads images gets them with the question. | The block below sets what the model sees besides the text, and shows the same images for the selected part. | Read the block. Turn the pictures on only for a model that reads images. | Report: Limitations and extensions, classification |
| Geometry (heading) | The heading starts the section for the shape of the element as drawing code. The model reads it as words, so no picture is needed. | The block below sets what shape data goes into the request, and shows the same markup for the selected part. | Read the block. Turn the markup on for Jev or d3-edge when names and properties do not tell the shape. | Report: Limitations and extensions, classification |
| Geometry as text | The list chooses whether the shape goes into the request as SVG markup. SVG is a plain drawing format in metres. | With SVG the model reads plan and side outlines of the part. This costs extra tokens for every question. | Keep Off for the fastest run. Choose SVG in the state for parts that look alike by name. | Report: Limitations and extensions, classification |
| Add the element in its bounding box | The switch adds the part inside its own box, with the outlines of nearby parts cut at the box. | On: the model sees the neighbours by type and tag, but never their answers. It reads more tokens. Off: it reads the part alone. | Turn it on when the place of a part tells what it is. Keep it off for a small request. | Report: Limitations and extensions, classification |
| Calibration (heading) | The heading starts the section for the scaling of the confidence. The scaling has a separate temperature for each question. | The block below makes the confidence match how often the answers are right, so good answers need no review. | Read the block. Click Calibrate on rules when the model is new to you. | Report: Limitations and extensions, classification |
| Backend | The list chooses where d3-edge runs. In the browser uses WebGPU and downloads the model. Endpoint calls a server that has a Jev style API. | The browser choice works offline after the download. It reads pictures only with an export that has a vision graph. The server choice can send pictures. | Choose Endpoint when you run vllm-sr serve. Choose In the browser to stay offline. | Report: Limitations and extensions, classification |
| Run on | The list chooses the device for d3-edge in the browser. Auto needs WebGPU with 16-bit floats. WASM runs on the processor and needs a lot of memory. | Auto refuses to start when the graphics card cannot take the model. WASM starts but is very slow. | Keep Auto. Choose WASM only to test on a computer with no usable graphics card. | Report: Limitations and extensions, classification |
| Model repository | The box holds a Hugging Face repository of ONNX files, or the web address of a folder with them. The viewer checks the manifest first. | A wrong name makes the check fail with a message. No large file arrives until the check is good. | Keep warsang/d3-edge-web for text. Type the address of your own export folder to read pictures too. | Report: Limitations and extensions, classification |
| Revision | The box holds the commit of the repository. A commit hash pins the files, so the answers stay repeatable. For a folder address it is only a label. | A fixed commit keeps the files the same from day to day. A branch name can bring new files without notice. | Keep the pinned hash. Type a new hash only after you check the new files. Change the label when you export again to the same folder. | Report: Limitations and extensions, classification |
| File address | The box holds the web address that serves the model files. Use another address for a mirror or your own proxy. | A bad link makes every download fail with a message. A mirror can work when the main site does not answer. | Keep the default. Type the address of your mirror when the main site does not answer. | Report: Limitations and extensions, classification |
| Download model | The button confirms the download of the model files. The text above it gives the size. | The files come to this device once and stay in the browser. The browser fetches nothing before you click. | Read the size. Click the button to download and test. Click Cancel to keep the disk free. | Report: Limitations and extensions, classification |
| Images | The list chooses the pictures. The element alone, the element in its bounding box with nearby parts in grey, or both. | With Off the model reads text only. With both it gets the element alone first, then the element in its surroundings. | Choose Both pictures when the text is thin. Keep Off for the fastest run. | Report: Limitations and extensions, classification |
| Picture style | The list chooses how the pictures are drawn. Render is shaded. Line drawing is black lines on white, with no shading. | Lines alone make a small file and show the outline of the shape. Soft light shows the surface and the colour of the part. | Keep Render to start. Try Line drawing when the shape of the part matters more than its surface. | Report: Limitations and extensions, classification |
| Add a plan view | The switch adds a second picture of the element alone, seen from above. | On: the request grows by one picture and the model sees the footprint of the part. Off: the model gets the axonometric picture only. | Turn it on for flat parts such as slabs. Keep it off for the fastest run. | Report: Limitations and extensions, classification |
| Box margin (%) | The number sets how far the box around the element grows, in percent of its longest side. The box never grows less than 0.5 m. | A larger number shows more of the surroundings. A smaller number shows only the parts that touch the element. | Keep 25. Raise it to show more of the room around a small part. | Report: Limitations and extensions, classification |
| Image size | The number sets the width and height of each picture in pixels, from 256 to 512 in steps of 32. | A larger picture shows more detail. A smaller picture is faster and cheaper to send. | Keep 384. Raise it for small parts. Lower it for a slow link. | Report: Limitations and extensions, classification |
| Send images to Jev | The switch lets the viewer send the pictures to a Jev endpoint. The feature is untested, because Jev is not known to read images. | On: each request grows by the size of the pictures. Off: the endpoint gets text only, as before. | Keep it off. Turn it on only for a server that reads images. | Report: Limitations and extensions, classification |
| Calibration | The list chooses the scaling of the confidence. Auto uses numbers shipped for the model. Fitted uses numbers from your model. Manual uses your numbers. Off keeps the raw answer. | Without scaling, most answers look unsure and wait for review. With scaling, the confidence follows how often the answers are right. | Keep Auto. Click Calibrate on rules to switch to Fitted. Choose Off to compare. | Report: Limitations and extensions, classification |
| Temperature: discipline | The number scales the confidence of the discipline answer. A number below 1 sharpens it. A number above 1 flattens it. | The chosen label never changes. Only the shown confidence and the review flag change. | Type a number from 0.05 to 50. Check the table after the change. | Report: Limitations and extensions, classification |
| Temperature: sub-discipline | The number scales the confidence of the sub-discipline answer. A number below 1 sharpens it. A number above 1 flattens it. | The chosen label never changes. Only the shown confidence and the review flag change. | Type a number from 0.05 to 50. Check the table after the change. | Report: Limitations and extensions, classification |
| Temperature: division | The number scales the confidence of the MasterFormat division answer. A number below 1 sharpens it. A number above 1 flattens it. | The chosen label never changes. Only the shown confidence and the review flag change. | Type a number from 0.05 to 50. Check the table after the change. | Report: Limitations and extensions, classification |
| Temperature: building | The number scales the confidence of the yes or no answer about the building. A number below 1 sharpens it. A number above 1 flattens it. | The answer never flips at 0.5. Only the distance from 0.5 changes. | Type a number from 0.05 to 50. Check the table after the change. | Report: Limitations and extensions, classification |
| Calibrate on rules | The button fits a temperature for each question. It uses the parts that the rules label with confidence as proxy labels. | The model runs once for each kind of part. Afterwards the table shows the numbers before and after for a held-out share. | Click the button on a model with many parts that the rules know. Read the table. A rule can be wrong. | Report: Limitations and extensions, classification |
| Forget fit | The button deletes the fitted temperatures of the chosen model from this browser. | The list then falls back to the shipped numbers. Stored answers stay. | Click the button before you fit again on other data. | Report: Limitations and extensions, classification |
| Status line | The line shows the last message, such as the number of results and calls. | It tells you what happened and whether something failed. | Read the line after each run. | Report: Limitations and extensions, classification |

## Search bar

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| Search box | The text box finds objects, commands, presets, saved views, sets and settings. It also runs a WHERE query and quantity sums. | Type a few letters and a ranked list opens below. A query shows how many objects match. A sum shows a total. | Press the slash key or Ctrl+K. Type a name, a class or a setting. Start with where to run a query. Start with count or sum for a total. Press Enter to act. | Report: Appendix I, Presets and keyboard |
| Quantity card | The card shows the short answer of a count or sum from the search box. The console holds the details. | A small see-through note appears under the top box with the total. It fades by itself after a few seconds. | Read the total. Keep the pointer on the card to keep it. Click the card to copy the text. Press Escape to close it. | Report: Appendix I, Presets and keyboard |
| Search button | The button opens the text box on a small screen. The box then fills the width. | Tap it and a field for typing opens across the full top edge. | Tap the magnifier icon. Type a word. | Report: Appendix I, Presets and keyboard |
| Result row | The row names a match. A click acts on it, and Shift adds an object to the selection. | Click an item and the viewer does the job at once. An object under the pointer lights up in the picture. | Click the row or press Enter on it. Hold Shift to add an object to the selection. | Report: Appendix I, Presets and keyboard |

## Status ba

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
|  | The bar shows the model, the x-ray state, the bucket counts, the element under the pointer and the frame time. | This thin line at the bottom tells you what you look at and how fast the picture draws. Red text is a message. | Rest the pointer on the line for all details. Click the info button or the model name for the model credits. | Report: Onboarding checklist |

## Status bar

| Setting | Intent | Impact | Use | Ref |
| --- | --- | --- | --- | --- |
| Model name | The segment names the model and counts its elements. A click opens the details and the credits of the models. | It tells you which building you look at and how many parts it has. Click it to see where it comes from. | Click the segment to read the credits of the built-in models. | Report: Onboarding checklist |
| Details button | The button opens a panel with the timings of Algorithm 1 and 2, the ray count and the model credits. | Click it and a small box opens with every number and the source of each demo building. | Click the button to open the box. Click it again or outside the box to close it. | Report: Algorithm 2 |
| Dismiss button | The button removes the red message from the bar. | Click the cross and the red text goes away. The rest stays as it is. | Click the cross after you read the message. | Report: Onboarding checklist |
