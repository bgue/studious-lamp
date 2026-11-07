# Deferred side quests

One line each: what, why deferred, where it came from.

- WBS node workflow and constraint opt-in on `awp.WBSNode` (`start`, `complete`): no wave 2 demo clause needs it and it overlaps I5 progress; wave 3. ADR-0024 plan check F10.
- Rule "a new blocking constraint on an Issued IWP puts it On hold" (`field-work-packaging.md` line 58): not built in P2-I2; owner of the rule is open (candidate: S4 hook calling `HoldIwp` logic as the module). STATE Q1.
- Automatic constraint population from requisitions, scaffold and purchase orders; clear-on-target-state rules; constraints on correspondence and schedule activities: wave 3. ADR-0024.
