// Help texts for every setting of the viewer. Intent and Use are in ASD-STE100 style English (Simplified Technical
// English) with the graphics vocabulary defined in GLOSSARY. Impact is the plain-language translation for a person who
// has not read the report. docs/SETTINGS.md is generated from this file (npm run docs).
// The popover shows the lines in this order: title, Intent, Impact, Use, Ref.
// Rules, checked by tests/help-text.test.ts:
//   - one instruction per sentence, at most 20 words, active voice, present tense
//   - the Use line is in the imperative mood and no sentence starts with a gerund
//   - no "e.g.", no "etc.", no parentheses; numbers as digits; units after a space
//   - the Ref line starts with "Report:" and names a section of the report, with the algorithm line when it has one
//   - the Impact line says what the person sees or feels change on screen, in everyday words (grade 6 to 8), at least
//     6 words, differs from Intent, and uses none of the glossary terms, none of the words of the control's own name
//     or folder title, and none of the technical words listed in tests/help-text.test.ts. For a slider it says what
//     happens at each end, for a switch what happens on and off, for a list what each choice looks like.
// Keep this file free of imports and of non-erasable TypeScript syntax: tools/gen-settings-doc.mjs loads it with Node.
//
// Keys. Folder entries use the folder title. Control entries use "<folder title>/<control name>". Matching is exact
// first and then ignores case, spaces and punctuation, so "occluderScope" and "occluder scope" find the same entry.
// The pattern "Class styles/*" stands for the folder of one object class; the text {class} becomes the class name.

export interface HelpEntry {
  intent: string;
  /** Plain-language effect on screen. Shown after Intent. */
  impact: string;
  use: string;
  ref: string;
}

const h = (intent: string, impact: string, use: string, ref: string): HelpEntry => ({ intent, impact, use, ref });

/** Terms used in the texts. One meaning per term. */
export const GLOSSARY: ReadonlyArray<{ term: string; definition: string }> = [
  { term: 'alpha', definition: 'The opacity of an object. The value 1 is solid and the value 0 is invisible.' },
  { term: 'occluder', definition: 'A context object that is host or near. Only occluders change alpha.' },
  { term: 'sightline', definition: 'A straight line from a sample point on a focus object to the camera.' },
  { term: 'focus', definition: 'The objects of interest, such as the selected duct run. The viewer draws focus objects solid and in front.' },
  { term: 'context', definition: 'The objects that can ghost, such as slabs, walls, beams and columns on nearby storeys.' },
  { term: 'host', definition: 'A context object that intersects or contains a focus object.' },
  { term: 'near', definition: 'A context object that is inside the buffer of a focus object and is not a host.' },
  { term: 'far', definition: 'A context object that is neither host nor near. The report never ghosts a far object.' },
  { term: 'buffer', definition: 'The distance around a focus object inside which a context object counts as near.' },
  { term: 'ghost', definition: 'To draw an object with an alpha below 1, so that the focus shows through it. A ghost is an object drawn this way.' },
  { term: 'edge pass', definition: 'A drawing step that adds outlines at the sharp edges of objects.' },
  { term: 'bloom', definition: 'A soft glow around the bright parts of the image. The viewer applies it to the focus only.' },
  { term: 'depth of field', definition: 'A blur of the image parts that are far from the focal distance of the camera.' },
  { term: 'order-independent transparency', definition: 'A method that blends transparent surfaces without sorting them. The viewer uses weighted blended transparency.' },
  { term: 'storey', definition: 'A level of the building. An object belongs to at most 1 storey.' },
  { term: 'tier', definition: 'The rank of an object category. An object of a higher tier ghosts the objects of a lower tier.' },
  { term: 'pin', definition: 'A rule that keeps the alpha of an object at or above a floor.' },
  { term: 'floor', definition: 'The lowest alpha that an object may have. A pin, a class style or a hide sets it.' },
  { term: 'explode', definition: 'To move objects apart, so that objects behind others become visible.' },
  { term: 'sweep', definition: 'A plane that moves from the camera side through the occluders and reveals the focus behind them.' },
  { term: 'keyframe', definition: 'A saved camera pose together with the selection and the effect switches. A fly-through connects keyframes.' },
  { term: 'bucket', definition: 'The result class of an object after classification. The buckets are focus, host, near and far.' },
  { term: 'class', definition: 'The IFC type of an object, such as IfcSlab or IfcDuctSegment.' },
  { term: 'sample', definition: 'A point on the surface of a focus object. Each sample casts 1 ray to the camera.' },
  { term: 'layer', definition: 'The position of an occluder along a ray. Layer 0 is the occluder nearest the camera.' },
  { term: 'occlusion', definition: 'The fraction of the rays that an occluder blocks. The value is between 0 and 1.' },
  { term: 'importance', definition: 'The product of occlusion, raised to gamma, and the proximity weight. It sets how far the alpha falls.' },
  { term: 'proximity weight', definition: 'A number from 0 to 1 that falls with the distance of a near object from the focus. A host has weight 1.' },
  { term: 'ambient occlusion', definition: 'A shading effect that darkens creases and contact areas.' },
  { term: 'vignette', definition: 'A darkening of the image towards its corners.' },
  { term: 'motion blur', definition: 'A blend of successive frames that smears fast camera moves.' },
  { term: 'fly-through', definition: 'A camera move along a smooth path through the keyframes.' },
  { term: 'turntable', definition: 'A slow orbit of the camera around the model.' },
  { term: 'dolly', definition: 'A camera move along the run of the focus objects.' },
];

/** Folder entries, in panel order. */
export const FOLDER_HELP: Record<string, HelpEntry> = {
  'X-ray': h(
    'The panel holds every setting of the X-ray viewer. Each folder groups the settings of a stage.',
    'This panel changes how the building looks on screen. Open a folder to find the controls for one part of the picture.',
    'Open a folder to see its settings. Hover over a setting for 350 ms to read its help.',
    'Report: Purpose',
  ),
  'Classification (Alg 1)': h(
    'The folder holds the settings of the static classification. The classification sorts each context object into host, near or far.',
    'These controls pick which walls and slabs fade around the selected item. Change one and the faded group grows or shrinks.',
    'Change a value here to move objects between the buckets. The camera does not affect these settings.',
    'Report: Algorithm 1, lines 1 to 11',
  ),
  'Sightlines (Alg 2)': h(
    'The folder holds the settings of the sightline test. The test runs after each camera move and sets the target alpha of each occluder.',
    'These controls set how much the walls and slabs in the way fade out. They also set how fast the fade happens.',
    'Change a value here to make the ghosting stronger, weaker or faster.',
    'Report: Algorithm 2, lines 1 to 12',
  ),
  Display: h(
    'The folder holds the settings that only change how the viewer draws. They do not change the classification.',
    'These controls change the outlines and colours of faded parts. They also decide whether distant parts stay in the picture.',
    'Change a value here to adjust outlines, ghost colour and the far objects.',
    'Report: Rendering in Bonsai/Blender',
  ),
  'Overrides (Alg 7)': h(
    'The folder holds the settings of the opacity floors. A floor stops an object from ghosting below a given alpha.',
    'This folder sets how strongly protected parts resist fading. A higher value keeps them easier to see.',
    'Change the pin floor here. Use the buttons of the X-ray folder to pin or hide objects.',
    'Report: Appendix C, Algorithm 7',
  ),
  'Open model': h(
    'The folder holds the controls that open a model file from your own computer. The viewer reads the file in the browser. No data leaves your computer.',
    'These controls let you look at your own building file. Your file stays on your computer and goes nowhere else.',
    'Click Open IFC or glb file to choose a file. Drop files on the viewer for the same action.',
    'Report: Appendix B, WebGL',
  ),
  'Class styles': h(
    'The folder holds the styles of the object classes. A style sets alpha limits, a floor, a hide flag and a colour for a class.',
    'This folder lets you set the look of each kind of building part, such as walls or slabs. Changes show at once.',
    'Open the Classes folder to edit a class. Use the buttons to reset, export or import all styles.',
    'Report: Appendix C, pin sources',
  ),
  Classes: h(
    'The folder lists 1 sub folder for each class in the model. The number after a class name is its object count.',
    'This folder lists every kind of building part in the model. Open one to restyle all parts of that kind.',
    'Open the sub folder of a class to change its style.',
    'Report: Appendix C, pin sources',
  ),
  'Class styles/*': h(
    'The folder sets the style of the class {class}. The style applies to every object of that class.',
    'Every part of the kind {class} changes together. Open the folder to change how they fade, show or look.',
    'Open the folder to change the class. Click Reset this class to remove your edits.',
    'Report: Appendix D, category priority',
  ),
  Cinematic: h(
    'The folder holds optional visual effects and camera moves. The effects do not change the classification or the alpha of any object.',
    'This folder adds film-style looks and camera moves. None of them change which parts fade.',
    'Open a sub folder to change an effect. Turn effects off to gain frame rate.',
    'Report: Limitations and extensions',
  ),
  'Camera fly-to': h(
    'The folder controls the camera move that follows a new selection.',
    'These controls decide whether the view glides toward each item you select. When off, the view stays where it is.',
    'Turn the move on to keep the focus in view. Turn it off to move the camera by hand.',
    'Report: Limitations and extensions',
  ),
  'Scene dressing': h(
    'The folder controls the sky, the fog, the lights and the ground shadow. They improve the look and do not change the result.',
    'These controls add a sky colour, haze and soft shading to the picture. Turn them off for plain flat colours.',
    'Turn the dressing off to see plain colours. Reduce the fog if distant objects look washed out.',
    'Report: Limitations and extensions',
  ),
  'Focus bloom': h(
    'The folder controls the glow around the focus objects. Context objects never glow.',
    'These controls add a soft glow around the item you picked. Walls and slabs never glow.',
    'Turn the bloom on to find the focus quickly in a busy model.',
    'Report: Limitations and extensions',
  ),
  'Host edge glow': h(
    'The folder controls the glowing outline of host objects. The outline shows where the focus passes through the structure.',
    'These controls add a bright line around the walls and slabs that the selected item crosses.',
    'Turn the glow on to see the points where a run penetrates a slab or a wall.',
    'Report: Terminology, host',
  ),
  'Sweep reveal': h(
    'The folder controls the reveal in which a sweep plane moves from the camera through the occluders.',
    'These controls shape the quick wipe that opens a clear view when walls and slabs fade.',
    'Turn the reveal on to show the focus with a clear start. Turn it off to ghost at once.',
    'Report: Limitations and extensions',
  ),
  'Depth-graded ghosting': h(
    'The folder controls the tint of the ghosts by depth. A ghost far in front of the focus looks cooler and darker.',
    'These controls tint faded parts darker and bluer when they lie well in front of the selected item.',
    'Turn the grading on to read the depth order of the ghosts.',
    'Report: Limitations and extensions',
  ),
  Sightlines: h(
    'The folder controls the drawing of the sightlines of the focus. The viewer draws them for a short time and fades them out.',
    'These controls draw thin lines from the selected item to the camera for a moment. The lines show what blocks the view.',
    'Click Show sightlines to check which rays an occluder blocks.',
    'Report: Algorithm 2, lines 2 to 5',
  ),
  'AO + vignette (extra GPU cost)': h(
    'The folder controls ambient occlusion and the vignette. Both effects cost GPU time.',
    'These controls add soft shading in corners and darker picture corners. They look richer but can make the picture update slower.',
    'Turn the effects on for still images. Turn them off for a high frame rate.',
    'Report: Appendix B, WebGL',
  ),
  'Exploded view (picking stays unexploded)': h(
    'The folder controls the exploded view. The view moves objects apart so that the focus shows. A click selects objects at their original positions.',
    'These controls pull parts of the building apart. That opens a clear path to the item you want to see.',
    'Click Explode to move the objects. Select the mode and the distances first.',
    'Report: Limitations and extensions',
  ),
  'Fly-through': h(
    'The folder controls the fly-through. A fly-through is a smooth camera move through saved keyframes.',
    'These controls build a film-like camera trip from saved views. You can watch it or record a video.',
    'Add 2 or more keyframes. Click Play to run the move and Record to save a video.',
    'Report: Limitations and extensions',
  ),
  Turntable: h(
    'The folder controls the turntable. The camera orbits the model at a constant speed.',
    'These controls spin the picture slowly around the building so you see every side. It pauses while you use the mouse.',
    'Turn the auto-orbit on to show the model from all sides.',
    'Report: Limitations and extensions',
  ),
  'Dolly along run': h(
    'The folder controls the dolly. The camera follows the run of the focus objects.',
    'These controls glide the camera beside the selected pipe or duct, from one end to the other.',
    'Select a duct or pipe run. Click Play dolly to start the move.',
    'Report: Limitations and extensions',
  ),
  Tour: h(
    'The folder controls the tour. The tour selects the saved selection sets in turn.',
    'These controls visit your saved groups one by one. The picture glides to each group and stays a few seconds.',
    'Save 2 or more selection sets in the sidebar. Click Play tour to start.',
    'Report: Onboarding checklist',
  ),
  Rendering: h(
    'The folder holds the settings of the transparency method used for the ghosts.',
    'These controls change how overlapping see-through walls and slabs mix their colours. Cleaner mixing can make the picture slower.',
    'Turn on order-independent transparency if overlapping ghosts show the wrong blend order.',
    'Report: Appendix E, McGuire and Bavoil 2013',
  ),
  'Export / import': h(
    'The folder holds the actions that save, share and restore all settings of the viewer as JSON.',
    'These buttons save your settings to a file or bring them back. They also let you share your view with other people.',
    'Export the settings before an experiment. Import the file later to return to the same state.',
    'Report: Onboarding checklist',
  ),
  'Panel dock': h(
    'The dock holds this panel at the right edge of the window. It folds into a narrow rail.',
    'The settings area sits on the right and can fold into a thin strip. A folded strip gives the picture more room.',
    'Fold the dock to gain view area. Unfold it to change a setting.',
    'Report: Onboarding checklist',
  ),
  Sidebar: h(
    'The sidebar shows the model tree, the selection sets and the properties of the selected object.',
    'The left side lists the parts of the building and your saved groups. Pick a part to see it light up.',
    'Click an item to select it. Use the eye icon to hide it.',
    'Report: Onboarding checklist',
  ),
};

/** Control entries. */
export const CONTROL_HELP: Record<string, HelpEntry> = {
  // ------------------------------------------------------------------ root folder
  'X-ray/Model': h(
    'The list selects the model to load. The viewer replaces the current scene with the chosen model.',
    'Choose another name and the screen shows a different building after a short wait.',
    'Select a model name from the list. Wait until the loading message disappears.',
    'Report: Onboarding checklist',
  ),
  'X-ray/X-ray (X)': h(
    'The switch turns the X-ray mode on or off. In the off state every object keeps alpha 1.',
    'Turn it on and walls and slabs in the way fade so you can see inside. Turn it off and everything looks solid.',
    'Turn the switch off to compare with the plain model. Press the X key for the same action.',
    'Report: Purpose',
  ),
  'X-ray/Tiers mode': h(
    'The switch ranks the object categories in tiers. A tier ghosts only the objects of a lower tier that block it.',
    'On: slabs and walls fade the most, beams and columns fade less, and the selected item stays solid. Off: every blocking part follows one fade rule.',
    'Turn the switch on when several kinds of object compete for the view. Turn it off for a plain focus and context view.',
    'Report: Appendix D, Algorithms 8 and 9',
  ),
  'X-ray/Pin selected': h(
    'The button pins the selected objects. A pinned object keeps its alpha at or above the user pin floor.',
    'The items you picked stay fairly solid, even behind walls and slabs. Other parts keep fading as before.',
    'Select the objects first. Click the button to keep them clear behind ghosts.',
    'Report: Appendix C, pin sources',
  ),
  'X-ray/Hide selected': h(
    'The button hides the selected objects. A hidden object is not drawn and does not block any sightline.',
    'The items you picked vanish from the picture, and they no longer block the view of what lies behind.',
    'Select the objects that are in the way. Click the button to remove them from the view.',
    'Report: Appendix C, Algorithm 7',
  ),
  'X-ray/Clear pins/hides': h(
    'The button removes all user pins and all user hides. The class styles stay in force.',
    'Parts you protected or removed come back to normal. The picture returns to the automatic look.',
    'Click the button to return to the automatic result.',
    'Report: Appendix C, pin sources',
  ),
  'X-ray/Frame all (F)': h(
    'The button moves the camera so that the whole model is in view.',
    'The picture zooms and turns until the whole building fits on screen.',
    'Click the button when you lose the model. Press the F key for the same action.',
    'Report: Onboarding checklist',
  ),

  // ------------------------------------------------------------------ Classification (Alg 1)
  'Classification (Alg 1)/bufferBase': h(
    'The slider sets the base buffer in metres. A context object inside the buffer of a focus object is near.',
    'Move the slider right and more walls and slabs close to the selected item start to fade. Move it left and fewer fade.',
    'Increase the value to make more objects near. Decrease the value to keep the ghosting close to the focus.',
    'Report: Algorithm 1, line 4',
  ),
  'Classification (Alg 1)/bufferScale': h(
    'The slider sets how much the buffer grows with the cross section of a focus object. The buffer equals the base plus the scale times the cross section.',
    'Move the slider right and thick pipes and ducts pull more walls and slabs into the fade zone. At 0 every item reaches the same distance.',
    'Increase the value to give thick ducts a wider buffer. Set the value to 0 to use the base buffer for all objects.',
    'Report: Algorithm 1, line 4',
  ),
  'Classification (Alg 1)/bufferLo': h(
    'The slider sets the smallest buffer in metres. The buffer never falls below this value.',
    'Move the slider right and even thin pipes make walls and slabs close to them fade. Move it left and thin pipes affect fewer parts.',
    'Increase the value to stop thin pipes from getting a tiny buffer. Keep the value below the high limit.',
    'Report: Parameters and defaults',
  ),
  'Classification (Alg 1)/bufferHi': h(
    'The slider sets the largest buffer in metres. The buffer never rises above this value.',
    'Move the slider left and big ducts affect fewer walls and slabs. Move it right and they reach out to more of the building.',
    'Decrease the value to stop large ducts from ghosting distant structure. Increase the value to include more structure around large ducts.',
    'Report: Parameters and defaults',
  ),
  'Classification (Alg 1)/storeyBand': h(
    'The slider sets how many storeys above and below the focus storey count as context. Objects on other storeys are not context.',
    'At 0 only walls and slabs on the same level as the selected item can fade. Higher values add levels above and below.',
    'Set the value to 0 to use the storey of the focus only. Increase the value to include the storeys above and below.',
    'Report: Algorithm 1, line 2',
  ),

  // ------------------------------------------------------------------ Sightlines (Alg 2)
  'Sightlines (Alg 2)/samplesPerObject': h(
    'The slider sets how many sample points the test takes on each focus object. Each sample casts 1 ray to the camera.',
    'Move the slider right and the fade looks steadier but updates more slowly. Move it left and it updates faster but can flicker.',
    'Increase the value to get a smoother occlusion result. Decrease the value to run the test faster.',
    'Report: Algorithm 2, line 1',
  ),
  'Sightlines (Alg 2)/maxSamples': h(
    'The slider sets the upper limit of sample points for all focus objects together. The limit keeps the test fast for a large focus.',
    'Move the slider left and big selections update faster, but the fade may flicker. Move it right and the fade stays steady.',
    'Decrease the value if the frame rate falls during orbit. Increase the value if the ghosting flickers on a large run.',
    'Report: Algorithm 2, line 1',
  ),
  'Sightlines (Alg 2)/alphaMin': h(
    'The slider sets the lowest alpha that an occluder reaches. An occluder with full importance gets this alpha.',
    'Move the slider left and the walls and slabs in the way fade almost to nothing. Move it right and they stay more solid.',
    'Decrease the value to make blocking objects more transparent. Increase the value to keep them more solid.',
    'Report: Algorithm 2, line 9',
  ),
  'Sightlines (Alg 2)/alphaMax': h(
    'The slider sets the highest alpha of an occluder. An occluder that blocks nothing gets this alpha.',
    'Move the slider right and parts that block nothing look fully solid. Move it left and they look slightly faded.',
    'Increase the value to keep the context solid when it does not block. Decrease the value to ghost all occluders a little.',
    'Report: Algorithm 2, line 9',
  ),
  'Sightlines (Alg 2)/gamma': h(
    'The slider sets the exponent that shapes importance from occlusion. Importance equals occlusion to the power gamma times the proximity weight.',
    'Move the slider left and a part that blocks only a little still fades a lot. Move it right and only big blockers fade.',
    'Decrease the value below 1 to ghost an occluder that blocks only a few rays. Increase the value above 1 to ghost only strong blockers.',
    'Report: Algorithm 2, line 8',
  ),
  'Sightlines (Alg 2)/occluder scope': h(
    'The list sets which context objects take part in the ray test. The value near tests host and near objects. The value all tests far objects too.',
    'Choose all and a distant wall that blocks the view fades too. The other choice fades only parts close to the selected item.',
    'Select near to follow the report. Select all to ghost a far object that blocks the view.',
    'Report: Limitations and extensions, Far occluders note',
  ),
  'Sightlines (Alg 2)/far weight': h(
    'The slider sets the proximity weight of a far occluder when the scope is all. A far object has no proximity weight of its own.',
    'Move the slider right and distant walls that block the view fade more. At 0 they stay fully solid. It works only when the list above says all.',
    'Increase the value to ghost far blockers more. Set the value to 0 to keep far objects solid.',
    'Report: Limitations and extensions, Far occluders note',
  ),
  'Sightlines (Alg 2)/smoothingRate': h(
    'The slider sets the fraction of the alpha change that the viewer applies on each step. The value 1 turns the smoothing off.',
    'Move the slider left and walls and slabs fade slowly and calmly. Move it right and they follow the camera at once.',
    'Decrease the value to make alpha changes slow and calm. Increase the value to make the ghosts follow the camera at once.',
    'Report: Algorithm 2, line 11',
  ),
  'Sightlines (Alg 2)/layer weighting': h(
    'The list sets how stacked occluders on a ray share the credit. Front gives the occluder nearest the camera the most transparency, with a falloff per layer.',
    'Choose front and the slab closest to the camera fades most while slabs below it stay firmer. Choose budget and only the top few slabs fade. Choose uniform and every slab in a stack fades the same.',
    'Select front to see through a stack of slabs from the nearest slab. Select budget to ghost only the first layers. Select uniform to give all layers equal credit.',
    'Report: Algorithm 2, lines 2 to 5',
  ),
  'Sightlines (Alg 2)/layer falloff': h(
    'The slider sets the credit factor for each layer behind the nearest layer. It acts under front weighting. The value 0.5 gives credits 1, 0.5 and 0.25.',
    'Move the slider left and only the top slab of a stack fades while lower slabs stay firm. Move it right and lower slabs fade almost as much. It works only when the list above says front.',
    'Decrease the value to ghost mainly the nearest layer. Increase the value to ghost deeper layers almost as much.',
    'Report: Algorithm 2, lines 2 to 5',
  ),
  'Sightlines (Alg 2)/layer budget': h(
    'The slider sets how many layers per ray ghost under budget weighting. Deeper layers get no credit.',
    'Set it to 1 and only the top slab of a stack fades. Move it right and more slabs below fade too. It does nothing while the list two rows up says front or uniform.',
    'Set the value to 1 to ghost only the nearest layer. Increase the value to open the view through more layers.',
    'Report: Algorithm 2, lines 2 to 5',
  ),

  // ------------------------------------------------------------------ Display
  'Display/edgeAlpha': h(
    'The slider sets the alpha of the outlines drawn by the edge pass. An outline is never fainter than its object.',
    'Move the slider right and the outlines of faded walls and slabs get darker and easier to see. At 0 they fade along with their parts.',
    'Increase the value to see the outlines of ghosts clearly. Set the value to 0 to remove the outlines of ghosts.',
    'Report: Appendix B, WebGL',
  ),
  'Display/ghost desaturate': h(
    'The slider sets how much colour a ghost loses. The value 1 draws ghosts in grey.',
    'Move the slider right and faded parts turn grey, so the selected item stands out. Move it left and they keep their own colours.',
    'Increase the value to separate the ghosts from the focus by colour. Decrease the value to keep the material colours.',
    'Report: Rendering in Bonsai/Blender',
  ),
  'Display/focus in front': h(
    'The switch draws the focus objects on top of all other objects. The focus then stays visible behind solid structure.',
    'Turn it on and the selected item always shows, even behind a solid wall. Turn it off and solid walls can hide it.',
    'Turn the switch on to see the focus through any wall. Turn it off to let solid objects hide the focus.',
    'Report: Appendix B, WebGL',
  ),
  'Display/far mode': h(
    'The list sets how the far objects draw. The value opaque draws them normally. The value hidden removes them.',
    'Choose opaque and distant walls and slabs stay in the picture. Choose hidden and they disappear.',
    'Select hidden to see only the focus and its occluders. Select opaque to see the full model.',
    'Report: Algorithm 1, line 5',
  ),
  'Display/debug colour by bucket': h(
    'The switch paints each object with the colour of its bucket. Focus, host, near and far each have 1 colour.',
    'On: parts that the selected item crosses turn red, close ones turn orange and distant ones turn grey. Off: normal materials return.',
    'Turn the switch on to check the classification. Turn it off before you judge the final look.',
    'Report: Terminology',
  ),

  // ------------------------------------------------------------------ Overrides (Alg 7)
  'Overrides (Alg 7)/user pin floor': h(
    'The slider sets the lowest alpha of a pinned object. A pinned object never ghosts below this value.',
    'Move the slider right and protected parts stay more solid behind walls. At 0 they can fade out completely.',
    'Increase the value to keep pinned objects clearer. Set the value to 0 to let pinned objects fade fully.',
    'Report: Appendix C, pin sources',
  ),

  // ------------------------------------------------------------------ Open model
  'Open model/Open IFC or glb file': h(
    'The button opens a file picker for your own model files. The viewer reads the files in the browser and sends nothing out. You can also drop files on the viewer.',
    'Click and a window lets you pick a building from your computer. You can also drag it onto the picture.',
    'Click the button. Choose a model file from your computer. Read the status line for the result.',
    'Report: Appendix B, WebGL',
  ),
  'Open model/Cancel load': h(
    'The button stops a load in progress. The viewer keeps the current model.',
    'Click while a new building is coming in and it stops. The building you see now stays on screen.',
    'Click the button when a load takes too long or you chose the wrong file.',
    'Report: Appendix B, WebGL',
  ),
  'Open model/Load status': h(
    'The field shows the progress of a load, then the result or an error. You cannot edit it.',
    'The text shows progress while a building comes in. It then says whether it worked or what went wrong.',
    'Read the field after you choose a file. Read the error text if the model does not appear.',
    'Report: Appendix B, WebGL',
  ),

  // ------------------------------------------------------------------ Class styles
  'Class styles/Reset to config': h(
    'The button discards your edits of the class styles. The styles return to the config file and the model sidecar.',
    'Click and every change you made to the look of parts vanishes. Each kind of part returns to the look its files give it.',
    'Click the button to undo all class edits at once.',
    'Report: Appendix C, pin sources',
  ),
  'Class styles/Export JSON': h(
    'The button saves the effective class styles as the file xray.config.json.',
    'Click and your browser saves a small file with the looks you set for each kind of part. You can send the file to other people.',
    'Click the button to share the styles with a colleague. Put the file in the public folder to make it the default.',
    'Report: Onboarding checklist',
  ),
  'Class styles/Import JSON': h(
    'The button loads class styles from a JSON file. The loaded styles replace your earlier edits.',
    'Click, pick a look file, and the parts change to match it. Your earlier changes are gone.',
    'Click the button. Select a file. Check the result in the Classes folder.',
    'Report: Onboarding checklist',
  ),
  'Class styles/*/alpha max': h(
    'The slider sets the highest alpha of objects of the class {class}. These objects never draw above this alpha.',
    'Move the slider left and every part of this kind looks a little faded, even when nothing blocks the view. At 1 they look normal.',
    'Decrease the value to keep the class a little transparent at all times. Set the value to 1 for the normal look.',
    'Report: Appendix D, category priority',
  ),
  'Class styles/*/alpha min': h(
    'The slider sets the lowest alpha that the sightline test gives to objects of the class {class}.',
    'Move the slider right and parts of this kind fade less when they block the view. Move it left and they can fade almost away.',
    'Increase the value to protect the class from strong ghosting. Decrease the value to let the class fade more.',
    'Report: Algorithm 2, line 9',
  ),
  'Class styles/*/floor': h(
    'The slider sets the floor of objects of the class {class}. The alpha of these objects never falls below the floor.',
    'Move the slider right and parts of this kind stay more solid, even when they block the view. At 0 they can fade away fully.',
    'Increase the value to keep the class visible. Set the value to 0 to remove the floor.',
    'Report: Appendix C, pin sources',
  ),
  'Class styles/*/hidden': h(
    'The switch hides all objects of the class {class}. Hidden objects are not drawn and do not block sightlines.',
    'Turn it on and every part of this kind disappears from the picture. The things behind them show clearly.',
    'Turn the switch on to remove a class that is in the way.',
    'Report: Appendix C, Algorithm 7',
  ),
  'Class styles/*/color': h(
    'The colour box sets the base colour of objects of the class {class}.',
    'Pick a shade and every part of this kind takes that shade at once.',
    'Click the box. Pick a strong colour to find a class quickly.',
    'Report: Rendering in Bonsai/Blender',
  ),
  'Class styles/*/Reset this class': h(
    'The button removes all your edits of the class {class}. The class returns to the config and sidecar values.',
    'Click and the changes you made to that kind of part vanish. Its sliders return to their start values.',
    'Click the button to undo the changes of this class only.',
    'Report: Appendix C, pin sources',
  ),

  // ------------------------------------------------------------------ Cinematic: Camera fly-to
  'Camera fly-to/Fly to selection': h(
    'The switch moves the camera to the focus when you select an object. The move is smooth.',
    'On: the view glides toward each new item you pick. Off: the view stays where it is.',
    'Turn the switch on to keep the selection in view. Turn it off to keep the camera where it is.',
    'Report: Limitations and extensions',
  ),
  'Camera fly-to/Duration (ms)': h(
    'The slider sets the time of a camera fly-to in milliseconds.',
    'Move the slider right and the glide to a new item takes longer and looks calmer. Move it left and it feels quick.',
    'Increase the value for a slow and calm move. Decrease the value for a fast move.',
    'Report: Limitations and extensions',
  ),
  'Camera fly-to/Fly to focus now': h(
    'The button moves the camera to the focus objects at once.',
    'Click and the view glides back to the selected item. Use it after you drift away.',
    'Click the button after you orbit away from the focus.',
    'Report: Limitations and extensions',
  ),
  'Camera fly-to/Staggered reveal': h(
    'The switch delays the fade of each occluder by its distance from the focus. The transparency spreads outward from the focus.',
    'On: walls and slabs fade one after another, spreading outward from the selected item. Off: they all fade together.',
    'Turn the switch on to show the ghosting as a ripple. Turn it off to ghost all occluders at the same time.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Scene dressing
  'Scene dressing/Sky, fog, lights': h(
    'The switch adds a gradient sky, distance fog and a key and fill light.',
    'On: a soft backdrop, thin haze and gentle shading appear. Off: the background turns plain and the shading goes flat.',
    'Turn the switch on for a pleasant still image. Turn it off to see the plain colours.',
    'Report: Limitations and extensions',
  ),
  'Scene dressing/Fog strength': h(
    'The slider sets how strongly distance fog fades far objects into the sky.',
    'Move the slider right and distant parts melt into a pale haze. Move it left and every part keeps its full colour.',
    'Increase the value to push distant structure back. Decrease the value if the model looks washed out.',
    'Report: Limitations and extensions',
  ),
  'Scene dressing/Ground shadow plane (+1 draw)': h(
    'The switch adds a soft shadow plane under the model. It costs 1 extra draw call.',
    'On: a soft dark patch appears under the building, so it looks like it rests on something. Off: it looks like it floats.',
    'Turn the switch on to anchor the model to the ground. Turn it off to save a draw call.',
    'Report: Appendix B, WebGL',
  ),
  'Scene dressing/Shadow strength': h(
    'The slider sets the darkness of the ground shadow.',
    'Move the slider right and the dark patch under the building gets darker. Move it left and it almost vanishes.',
    'Increase the value for a clear shadow. Decrease the value for a faint shadow.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Focus bloom
  'Focus bloom/Selective bloom': h(
    'The switch adds a bloom around the focus objects only. Context objects do not glow.',
    'On: a soft glow surrounds the item you picked, so it jumps out of a busy picture. Off: it looks plain.',
    'Turn the switch on to find the focus in a busy view.',
    'Report: Limitations and extensions',
  ),
  'Focus bloom/Strength': h(
    'The slider sets the brightness of the bloom.',
    'Move the slider right and the glow around the selected item gets brighter. Very high values wash out its colour.',
    'Increase the value for a strong glow. Decrease the value if the focus colour washes out.',
    'Report: Limitations and extensions',
  ),
  'Focus bloom/Radius': h(
    'The slider sets how far the bloom spreads.',
    'Move the slider right and the glow spreads wider and softer. Move it left and it hugs the item tightly.',
    'Increase the value for a wide, soft glow. Decrease the value for a tight glow.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Host edge glow
  'Host edge glow/Edge glow': h(
    'The switch adds a glowing outline to host objects. The outline marks where the focus meets the structure.',
    'On: a bright line shows around the walls and slabs that the selected item crosses. Off: they look normal.',
    'Turn the switch on to find penetrations of slabs and walls.',
    'Report: Terminology, host',
  ),
  'Host edge glow/Include near': h(
    'The switch adds the outlines of near objects to the glow. Without it only host objects glow.',
    'On: walls and slabs close to the selected item get the bright line too. Off: only the ones it crosses get it.',
    'Turn the switch on to see all occluders. Turn it off to see the host objects only.',
    'Report: Terminology, near',
  ),
  'Host edge glow/Additive': h(
    'The switch adds the glow colour to the image instead of replacing the colour below.',
    'On: the line adds light to what lies behind it, so it shines on dark parts. Off: it looks flat and solid.',
    'Turn the switch on for a bright glow on dark ghosts. Turn it off for a flat outline.',
    'Report: Appendix B, WebGL',
  ),
  'Host edge glow/Strength': h(
    'The slider sets the brightness of the edge glow.',
    'Move the slider right and the bright line gets bolder and brighter. Move it left and it almost disappears.',
    'Increase the value to make the outline stand out. Decrease the value for a quiet outline.',
    'Report: Limitations and extensions',
  ),
  'Host edge glow/Colour': h(
    'The colour box sets the colour of the edge glow.',
    'Pick a shade for the bright line around crossed walls and slabs. A shade unlike the selected item makes it stand out.',
    'Click the box. Pick a colour that differs from the focus colour.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Sweep reveal
  'Sweep reveal/Sweep reveal': h(
    'The switch starts a sweep when the ghosting changes. The sweep moves from the camera through the occluders.',
    'On: when walls and slabs fade, a bright stripe wipes from the camera toward the selected item. Off: they fade at once.',
    'Turn the switch on to show the focus with a clear start. Turn it off to ghost at once.',
    'Report: Limitations and extensions',
  ),
  'Sweep reveal/Mode': h(
    'The list selects the reveal style. The value stagger delays each occluder. The value sweep moves a plane. The value both uses sweep and stagger.',
    'Stagger makes parts fade one by one, spreading outward. The second choice wipes a bright stripe across the picture. Both does the two together.',
    'Select sweep for a clean plane. Select stagger for a ripple from the focus. Select both for the full effect.',
    'Report: Limitations and extensions',
  ),
  'Sweep reveal/Duration (ms)': h(
    'The slider sets the time of the sweep in milliseconds.',
    'Move the slider right and the wipe takes longer and looks slower. Move it left and it ends in a blink.',
    'Increase the value for a slow reveal. Decrease the value for a quick reveal.',
    'Report: Limitations and extensions',
  ),
  'Sweep reveal/Band width (m)': h(
    'The slider sets the width of the bright band at the sweep plane in metres.',
    'Move the slider right and the bright stripe gets thicker and easier to spot. Move it left and it shrinks to a thin line.',
    'Increase the value for a wide band that is easy to see. Decrease the value for a thin line.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Depth-graded ghosting
  'Depth-graded ghosting/Depth grading': h(
    'The switch tints the ghosts by their depth in front of the focus. Far ghosts look cooler and darker.',
    'On: faded parts that sit well in front of the selected item look darker and bluer. Off: all faded parts share one tint.',
    'Turn the switch on to read the depth order of the ghosts.',
    'Report: Limitations and extensions',
  ),
  'Depth-graded ghosting/Strength': h(
    'The slider sets the largest mix of the cool dark tone into a ghost.',
    'Move the slider right and the dark blue tint on faded parts gets heavier. Move it left and the tint is hard to see.',
    'Increase the value to grade the depth strongly. Decrease the value for a subtle grade.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Sightlines
  'Sightlines/Show sightlines': h(
    'The button draws the sample rays from the focus to the camera for a short time.',
    'Click and thin lines run from the selected item to the camera, then vanish. Orange lines hit something and blue lines have a free view.',
    'Click the button to see which occluders block the focus. Orbit first to choose the view.',
    'Report: Algorithm 2, lines 2 to 5',
  ),
  'Sightlines/On selection': h(
    'The switch draws the sightlines each time you select an object.',
    'On: the thin lines appear each time you pick an item. Off: they appear only when you click the button.',
    'Turn the switch on to inspect every selection. Turn it off for a clean view.',
    'Report: Algorithm 2, lines 2 to 5',
  ),
  'Sightlines/Style': h(
    'The list selects how the rays draw. The value lines draws segments. The value dots draws hit points. The value both draws lines and dots.',
    'Choose lines for long thin strokes. Choose dots for small spots where each line meets a wall or slab. Choose both to see the two together.',
    'Select lines to follow the paths. Select dots to see where the rays hit.',
    'Report: Algorithm 2, lines 2 to 5',
  ),
  'Sightlines/Which rays': h(
    'The list selects which rays draw. The value blocked draws rays that hit an occluder. The value unblocked draws the free rays.',
    'Choose blocked to see only the lines that hit a wall or slab. Choose unblocked to see the lines with a free view. Choose all to see both.',
    'Select blocked to find the cause of ghosting. Select unblocked to see the free view.',
    'Report: Algorithm 2, line 7',
  ),
  'Sightlines/Colour by hit': h(
    'The switch colours each ray by its result. Blocked rays and free rays get different colours.',
    'On: lines that touch a wall or slab turn orange and free lines turn blue. Off: every line looks the same pale shade.',
    'Turn the switch on to separate blocked rays from free rays at a glance.',
    'Report: Algorithm 2, line 7',
  ),
  'Sightlines/Max rays': h(
    'The slider sets the largest number of rays to draw.',
    'Move the slider right and more lines show, so the picture gets busier. Move it left and only a few lines show.',
    'Decrease the value to keep the picture clear. Increase the value to show more samples.',
    'Report: Algorithm 2, line 1',
  ),
  'Sightlines/Fade (s)': h(
    'The slider sets the time in seconds before the drawn rays fade out.',
    'Move the slider right and the lines stay on screen longer. Move it left and they vanish quickly.',
    'Increase the value to study the rays longer. Decrease the value to clear the view sooner.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: AO + vignette
  'AO + vignette (extra GPU cost)/AO (GTAO, half res)': h(
    'The switch adds ambient occlusion at half resolution. It darkens creases and contact areas.',
    'On: soft dark shading appears in corners and where parts meet, which gives the picture a richer look. Off: surfaces look flat but update faster.',
    'Turn the switch on for still images with more depth. Turn it off for a high frame rate.',
    'Report: Appendix B, WebGL',
  ),
  'AO + vignette (extra GPU cost)/AO radius (m)': h(
    'The slider sets the reach of the ambient occlusion in metres.',
    'Move the slider right and the dark shading spreads over wider gaps. Move it left and it stays in tight corners.',
    'Increase the value to shade larger gaps. Decrease the value to shade only tight corners.',
    'Report: Appendix B, WebGL',
  ),
  'AO + vignette (extra GPU cost)/AO intensity': h(
    'The slider sets the strength of the ambient occlusion shading.',
    'Move the slider right and the dark shading in corners gets deeper. Move it left and the shading is hard to notice.',
    'Increase the value for dark creases. Decrease the value for a light touch.',
    'Report: Appendix B, WebGL',
  ),
  'AO + vignette (extra GPU cost)/Vignette': h(
    'The switch darkens the image towards its corners.',
    'On: the picture corners turn darker, which draws the eye to the middle. Off: the whole picture looks even.',
    'Turn the switch on to draw the eye to the centre. Turn it off for an even image.',
    'Report: Limitations and extensions',
  ),
  'AO + vignette (extra GPU cost)/Vignette darkness': h(
    'The slider sets how dark the corners become.',
    'Move the slider right and the picture corners get very dark. Move it left and they stay light.',
    'Increase the value for strong corners. Decrease the value for a faint effect.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Exploded view
  'Exploded view (picking stays unexploded)/Explode': h(
    'The button moves the objects apart with an animation. The same button moves them back.',
    'Click and parts of the building slide apart, so hidden parts come into sight. Click again and they slide back.',
    'Select an object first. Click the button to open a path to the focus.',
    'Report: Limitations and extensions',
  ),
  'Exploded view (picking stays unexploded)/explode': h(
    'The list selects which objects move. The value auto picks the selection or its occluders. The value both moves the selection and its occluders.',
    'Choose which parts slide apart. Auto lets the program decide. The other choices move your chosen items, the parts in their way, or both.',
    'Select occluders to clear the view of a single object. Select selection to move the selected group apart.',
    'Report: Limitations and extensions',
  ),
  'Exploded view (picking stays unexploded)/Mode': h(
    'The list selects the way the objects move. The value radial moves them away from the centre. The value storeys separates the storeys.',
    'Radial pushes parts outward from the middle like a burst. The second choice lifts each level of the building apart. The third does both.',
    'Select radial for a classic exploded view. Select storeys to lift each storey apart. Select radial+storeys for both.',
    'Report: Terminology, storey',
  ),
  'Exploded view (picking stays unexploded)/Radial factor': h(
    'The slider sets the distance of the radial move as a multiple of the distance from the centre.',
    'Move the slider right and parts slide much further out. Move it left and the picture looks compact.',
    'Increase the value to push the objects far apart. Decrease the value for a compact view.',
    'Report: Limitations and extensions',
  ),
  'Exploded view (picking stays unexploded)/Storey gap (m)': h(
    'The slider sets the vertical gap in metres between neighbouring storeys.',
    'Move the slider right and the levels of the building lift further apart. Move it left and they sit close together.',
    'Increase the value to see each storey alone. Decrease the value to keep the storeys close.',
    'Report: Terminology, storey',
  ),
  'Exploded view (picking stays unexploded)/Min push (m)': h(
    'The slider sets the smallest radial move in metres. An object that is near the centre moves at least this far.',
    'Move the slider right and parts that sit very close to the middle still slide out clearly. At 0 they may barely move.',
    'Increase the value to clear objects that sit close to the focus. Set the value to 0 to turn it off.',
    'Report: Limitations and extensions',
  ),
  'Exploded view (picking stays unexploded)/Duration (ms)': h(
    'The slider sets the time of the explode move in milliseconds.',
    'Move the slider right and the parts take longer to slide apart or back. Move it left and they snap into place.',
    'Increase the value for a slow move. Decrease the value for a fast move.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Fly-through
  'Fly-through/Keyframes': h(
    'The field shows how many keyframes the fly-through holds. You cannot edit it.',
    'The number shows how many saved views the trip holds. You need at least 2 to watch it.',
    'Read the count before you play. Add at least 2 keyframes.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Add keyframe': h(
    'The button saves the current camera pose, selection and effect switches as a new keyframe.',
    'Click and the viewer saves the current camera position as one stop on the trip. The count goes up by 1.',
    'Move the camera to a view. Click the button to save it.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Remove last': h(
    'The button deletes the last keyframe.',
    'Click and the final stop on the trip disappears. The count goes down by 1.',
    'Click the button to undo the last keyframe you added.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Clear': h(
    'The button deletes all keyframes.',
    'Click and every stop on the trip disappears, so you can start again.',
    'Click the button to start a new fly-through.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Load from selection sets': h(
    'The button creates 1 keyframe for each saved selection set. Each keyframe frames its set.',
    'Click and the trip gets one stop for each saved group. Each stop looks at its group.',
    'Save selection sets in the sidebar first. Click the button to build a fly-through from them.',
    'Report: Onboarding checklist',
  ),
  'Fly-through/Seconds per segment': h(
    'The slider sets the time in seconds between 2 keyframes.',
    'Move the slider right and the trip takes longer between stops, so it feels calm. Move it left and it feels hurried.',
    'Increase the value for a slow move. Decrease the value for a quick reveal.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Play / stop': h(
    'The button starts or stops the fly-through along a smooth path through the keyframes.',
    'Click and the camera glides along the saved views like a film. Click again and the film ends.',
    'Click the button to play. Click it again to stop.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Record (webm download)': h(
    'The button plays the fly-through and records it as a webm video that the browser downloads.',
    'Click and the trip runs on its own while the viewer films it. Your browser then saves the video.',
    'Add the keyframes first. Click the button. Wait until the download starts.',
    'Report: Limitations and extensions',
  ),
  'Fly-through/Export JSON': h(
    'The button saves the keyframes as a JSON file.',
    'Click and your browser saves a small file holding your saved views. You can reuse it later or share it.',
    'Click the button to keep a fly-through or to share it.',
    'Report: Onboarding checklist',
  ),
  'Fly-through/Import JSON': h(
    'The button loads keyframes from a JSON file. The loaded keyframes replace the current ones.',
    'Click, pick a trip file, and its saved views replace the ones you have now.',
    'Click the button. Select a fly-through file.',
    'Report: Onboarding checklist',
  ),
  'Fly-through/Depth of field (playback)': h(
    'The switch adds depth of field during playback. The parts away from the focal distance blur.',
    'On: during the trip the main item stays crisp while the rest of the picture turns soft. Off: everything stays sharp.',
    'Turn the switch on for a film look. Turn it off for a sharp image and a high frame rate.',
    'Report: Appendix B, WebGL',
  ),
  'Fly-through/Aperture': h(
    'The slider sets the strength of the depth of field blur.',
    'Move the slider right and more of the picture around the main item turns soft. Move it left and more stays sharp.',
    'Increase the value for a shallow focus. Decrease the value for a deep focus.',
    'Report: Appendix B, WebGL',
  ),
  'Fly-through/Motion blur (playback)': h(
    'The slider sets how much of the previous frame mixes into the next frame during playback. Fast camera moves look smooth.',
    'Move the slider right and fast camera moves leave soft trails and look smoother during the trip. At 0 every picture stays crisp.',
    'Increase the value for recorded video. Set the value to 0 to see crisp frames.',
    'Report: Appendix B, WebGL',
  ),

  // ------------------------------------------------------------------ Cinematic: Turntable
  'Turntable/Auto-orbit': h(
    'The switch turns the camera around the model at a constant speed. It stops when you touch the view.',
    'On: the picture spins slowly around the building so you see every side. Off: it stays where you leave it.',
    'Turn the switch on to show the model from all sides.',
    'Report: Limitations and extensions',
  ),
  'Turntable/Speed (deg/s)': h(
    'The slider sets the orbit speed in degrees per second. A negative value turns the other way.',
    'Move the slider right and the spin gets faster. Values below zero spin the other way.',
    'Increase the value for a fast orbit. Use a negative value to reverse the direction.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Dolly
  'Dolly along run/Play dolly': h(
    'The button moves the camera along the run of the focus objects. The same button pauses the move.',
    'Click and the camera glides beside the selected pipe or duct, from end to end. Click again and it holds still.',
    'Select a duct or pipe run first. Click the button to start. Click it again to pause.',
    'Report: Limitations and extensions',
  ),
  'Dolly along run/Speed (m/s)': h(
    'The slider sets the speed of the dolly in metres per second.',
    'Move the slider right and the camera glides faster. Move it left and you have time to study every fitting.',
    'Increase the value for a fast move. Decrease the value to inspect fittings.',
    'Report: Limitations and extensions',
  ),
  'Dolly along run/Height offset (m)': h(
    'The slider sets the height of the camera above the run in metres.',
    'Move the slider right and the camera rises above the pipe and looks down on it. Below zero it travels under the pipe.',
    'Increase the value to look down on the run. Set the value to 0 to travel at the level of the run.',
    'Report: Limitations and extensions',
  ),
  'Dolly along run/Progress': h(
    'The slider shows and sets the position of the camera along the run. The value 0 is the start and the value 1 is the end.',
    'The slider shows how much of its path the camera has covered. Drag it to slide the camera back and forth by hand.',
    'Drag the slider to scrub along the run. The drag pauses the dolly.',
    'Report: Limitations and extensions',
  ),

  // ------------------------------------------------------------------ Cinematic: Tour
  'Tour/Play tour': h(
    'The button selects the saved selection sets in turn and flies to each. The same button stops the tour.',
    'Click and the picture visits your saved groups one by one, staying a few seconds on each. Click again and it ends.',
    'Save 2 or more selection sets first. Click the button to start. Click it again to stop.',
    'Report: Onboarding checklist',
  ),
  'Tour/Hold (s)': h(
    'The slider sets the time in seconds that the tour stays on each selection set.',
    'Move the slider right and the picture stays longer on each saved group. Move it left and the visits go quickly.',
    'Increase the value to give viewers time to read the view. Decrease the value for a short tour.',
    'Report: Onboarding checklist',
  ),
  'Tour/Loop': h(
    'The switch restarts the tour after the last selection set.',
    'On: after the last saved group, the visits start again from the first. Off: they end after the last.',
    'Turn the switch on for a continuous show. Turn it off to stop at the end.',
    'Report: Onboarding checklist',
  ),

  // ------------------------------------------------------------------ Rendering
  'Rendering/order-independent ghosts': h(
    'The switch draws the ghosts with weighted blended order-independent transparency. The method removes sorting errors where ghosts overlap.',
    'On: overlapping see-through walls and slabs mix cleanly, whichever one is in front. Off: the colours at overlaps may look wrong.',
    'Turn the switch on when overlapping ghosts show a wrong blend order. Turn it off to save GPU time.',
    'Report: Appendix E, McGuire and Bavoil 2013',
  ),
  'Rendering/depth weight': h(
    'The list sets the blend weight of a ghost fragment. The value paper lets a nearer ghost count more. The value flat uses the alpha only.',
    'Choose paper and the closer see-through part wins more of the colour. Choose flat and distant ones show through more evenly.',
    'Select paper to follow McGuire and Bavoil 2013. Select flat if distant ghosts look too faint.',
    'Report: Appendix E, McGuire and Bavoil 2013',
  ),
  'Rendering/OIT antialiasing': h(
    'The switch smooths the edges of ghosts that the transparency method draws. It uses 4 samples per pixel.',
    'On: the outlines of see-through parts look smooth instead of jagged. Off: they may show small stair steps but the picture updates faster.',
    'Turn the switch on for clean ghost edges. Turn it off to save GPU memory and time.',
    'Report: Appendix B, WebGL',
  ),
  'Rendering/float buffers': h(
    'The field shows whether the GPU supports the float colour buffers that the transparency method needs. You cannot edit it.',
    'The text tells you whether your graphics card can mix overlapping see-through parts cleanly. If it says no, the first switch in this folder stays unavailable.',
    'Read the field if the order-independent switch is disabled. Use a newer browser or GPU to enable it.',
    'Report: Appendix B, WebGL',
  ),

  // ------------------------------------------------------------------ Export / import
  'Export / import/Export JSON': h(
    'The button downloads all settings of the viewer as a JSON file. The file holds the classification, the sightlines, the styles and the effects.',
    'Click and your browser saves a small file with all your settings. Keep it to restore this look later.',
    'Click the button to keep a setup or to share it. Name the file after the project.',
    'Report: Onboarding checklist',
  ),
  'Export / import/Copy JSON': h(
    'The button copies all settings of the viewer to the clipboard as JSON text.',
    'Click and your settings go onto the clipboard as text. Paste them into a message or a note.',
    'Click the button. Paste the text into a message or a file.',
    'Report: Onboarding checklist',
  ),
  'Export / import/Import JSON': h(
    'The button loads settings from a JSON file. The viewer applies the values and reports any value it cannot use.',
    'Click, pick a settings file, and the viewer takes on those settings. It tells you about any value it cannot use.',
    'Click the button. Select a file that you exported before.',
    'Report: Onboarding checklist',
  ),
  'Export / import/Copy share URL': h(
    'The button copies a link that carries the main settings and the camera. The link opens the same view.',
    'Click and a web link goes onto the clipboard. A friend who opens it with the same building sees your picture.',
    'Click the button. Send the link to a colleague who uses the same model.',
    'Report: Onboarding checklist',
  ),
  'Export / import/Export Python dict': h(
    'The button downloads the settings as a Python dictionary. A script in Bonsai or Blender can read it.',
    'Click and your browser saves a text file of your settings for Blender users. They can read it in a script.',
    'Click the button when you port a setup to the Blender implementation.',
    'Report: Rendering in Bonsai/Blender',
  ),
  'Export / import/Reset to defaults': h(
    'The button sets all settings back to the defaults of the report. It clears your pins, hides and class edits.',
    'Click and every slider and switch returns to its starting value. Your protected and removed parts and style changes vanish too.',
    'Click the button to start again from a known state. Export your settings first.',
    'Report: Parameters and defaults',
  ),

  // ------------------------------------------------------------------ Panel dock
  'Panel dock/Collapse toggle': h(
    'The button folds the settings panel into a narrow rail and opens it again. The 3D view uses the freed width.',
    'Click and the settings area shrinks to a thin strip, so the picture gets wider. Click again and it opens.',
    'Click the button to gain view area. Press the ] key for the same action.',
    'Report: Onboarding checklist',
  ),

  // ------------------------------------------------------------------ Sidebar
  'Sidebar/Collapse toggle': h(
    'The button folds the sidebar into a narrow rail and opens it again. The 3D view uses the freed width.',
    'Click and the left side shrinks to a thin strip, so the picture gets wider. Click again and it opens.',
    'Click the button to gain view area. Press the [ key for the same action.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Model tab': h(
    'The tab shows the model tree. The tree groups objects by storey and by class.',
    'Click and the left side lists the parts of the building, grouped by level and kind.',
    'Click the tab to browse the model. Open a group to see its objects.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Sets tab': h(
    'The tab shows the saved selection sets of this model.',
    'Click and the left side shows your saved groups of parts. You can reuse a group in one click.',
    'Click the tab to save, apply, export or import selection sets.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Filter box': h(
    'The box filters the model tree by name, GlobalId or class. The count shows the matching objects.',
    'Type a few letters and the list shrinks to the parts that match. A small number tells you how many match.',
    'Type part of a name to find an object. Press Escape to clear the filter.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Eye icon': h(
    'The icon hides or shows the object or the group of its row. A hidden object is also a user hide.',
    'Click and the part, or the whole group, disappears from the picture. Click again and it returns.',
    'Click the icon to hide a row. Click it again to show the row.',
    'Report: Appendix C, pin sources',
  ),
  'Sidebar/Bucket dot': h(
    'The dot shows the bucket of the object after classification. The buckets are focus, host, near and far.',
    'The small mark tells you why a part looks the way it does. Blue means picked, red means crossed, amber means close and grey means distant.',
    'Read the dot to see why an object ghosts. Select a duct to see the dots change.',
    'Report: Terminology',
  ),
  'Sidebar/Expand arrow': h(
    'The arrow opens or closes a group in the model tree.',
    'Click and the group opens to show the parts inside it. Click again and it closes.',
    'Click the arrow to show the objects of the group.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Set name box': h(
    'The box holds the name for a new selection set.',
    'Type a label for a new saved group here. The label shows in the list after you save.',
    'Type a name. Press Enter to store the set.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Save selection': h(
    'The button stores the current selection as a new set with the typed name.',
    'Click and the viewer stores the parts you picked as a named group. The group appears in the list below.',
    'Select the objects. Type a name. Click the button to save.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Export sets': h(
    'The button downloads the selection sets of this model as a JSON file.',
    'Click and your browser saves a small file with all your saved groups. Keep it as a backup or send it to a colleague.',
    'Click the button to back up the sets or to share them.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Import sets': h(
    'The button loads selection sets from a JSON file. A set with the same name is replaced.',
    'Click, pick a file of saved groups, and they join your list. The new group takes the place of an old one with the same name.',
    'Click the button. Select a file.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Apply set': h(
    'The button replaces the selection with the objects of the set and frames them.',
    'Click and the parts of that group become your picked items, and the picture moves to show them.',
    'Click the button to jump to a saved view of the model.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Add set': h(
    'The button adds the objects of the set to the current selection.',
    'Click and the parts of that group join the items you already picked. The picked area grows.',
    'Click the button to build a larger focus from several sets.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Update set': h(
    'The button replaces the objects of the set with the current selection.',
    'Click and the group now holds the parts you picked at this moment. Its old parts drop out.',
    'Select the new objects. Click the button to overwrite the set.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Rename set': h(
    'The button changes the name of the set.',
    'Click, type a new label, and press Enter. The group keeps its parts and gets the new label.',
    'Click the button. Type a new name. Press Enter.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Delete set': h(
    'The button removes the set from the list. The objects stay in the model.',
    'Click and the group disappears from the list. The parts stay in the building.',
    'Click the button only when you no longer need the set.',
    'Report: Onboarding checklist',
  ),
  'Sidebar/Copy GlobalId': h(
    'The button copies the GlobalId of the first selected object to the clipboard.',
    'Click and the unique code of the picked part goes onto the clipboard. Paste it into another program to find the same part.',
    'Select an object. Click the button and paste the id into your BIM tool.',
    'Report: Onboarding checklist',
  ),
};

/** Every entry, folders first. The viewer and the tests read this record. */
export const HELP: Record<string, HelpEntry> = { ...FOLDER_HELP, ...CONTROL_HELP };
