# Classification tree

The **Model** tab of the left sidebar has a switch: **Model tree** (the IFC storeys, as before) and **By classification**. The second
view groups the same elements by what the classifier found out about them, whatever the file's own structure.

1. Classify with the facets on (Classification tab, **Facets: all** or **Classify**).
2. Click **By classification**. **Group by** offers **Construction** (Phase, Trade, IFC class), **Ownership** (Discipline,
   Sub-discipline, IFC class), **Envelope** (Placement, Material, IFC class) and **Standard (UniFormat II)** (A, A10, A1010). Pick
   **Custom** or change a level list to build your own (1 to 4 levels).
3. Each row shows a count, an amber share that needs review, the eye and **+set**. Elements with no value sit under **Not classified**.
4. In the Classification tab, **Colour by** paints the model by a facet and lists a legend. Click a legend row to isolate it.
   **Confidence shading** washes out the elements that need review.

**Save as set.** Every row is a query such as `XR_Trade.Code = 'CONC' and XR_Phase.Code = 'FRAME'`. **+set** (hover a row) opens the
criteria-set editor with it.

The keys are those of the model tree: arrows, Right and Left, Home and End, type-ahead, Enter, `*`, Ctrl+Space ([keyboard.md](keyboard.md#model-tree-keys)).

The UniFormat mapping is `public/classification/uniformat2.json` (rules from Phase, Placement, class, Trade and Discipline to a code);
**Mapping...** loads your own file. Details: [classify.md](classify.md#classification-tree-and-colours).
