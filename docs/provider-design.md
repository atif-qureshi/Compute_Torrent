# Provider and portal design alignment — 2026-11-08

## Scope

The existing native CustomTkinter provider now uses the portal's light neutral workspace, white bordered surfaces, ink text, restrained violet primary actions, compact navigation, and semantic connection colors. It remains a native desktop application. No webview migration or extra UI dependency was introduced.

## Implementation

`08-provider-node/05-desktop-app-shell/provider_views.py` owns reusable labels, buttons, panels, fields, navigation, setup, hardware, help, and dashboard presentation. The legacy `desktop/05-desktop-app-shell` copy matches. The existing entrypoint delegates its onboarding and dashboard rendering to this module. PyInstaller follows the normal module import; the candidate archive is checked separately.

Connection setup separates coordinator/enrollment, sharing limits, and runtime preparation. Enrollment is masked with an explicit reveal control. Hardware detection is separate from connection status. Overview, Hardware, Activity and Help have distinct views; hidden views retain their widget instances so existing asynchronous status targets remain valid. Navigating views preserves unsaved fields. Background hardware redraw preserves the selected view and unsaved layer-sharing choice. Native scrolling supports the defined 960×680 minimum; initial size is 1120×850.

Connect, Disconnect, Pause, runtime preparation, clipboard, resource reports, task state, contribution history and update controls retain existing callbacks. Registration still requires coordinator confirmation. Demo credits have no monetary value. Unknown hardware is described as unreported rather than synthesized telemetry.

Only the updater toolbar's presentation and notification color translation changed. Check/download/stage/install logic, update configuration, feeds, signing policy, version identifiers and security behavior are unchanged. Source AST regression checks verify the updater methods and primary connection methods match HEAD. No application update is published by this work.

## Validation and limits

Native Tk widget tests validate actual constructed controls, callback wiring, coordinator-confirmed status, navigation retention, masked enrollment, CUDA action availability, sharing-choice retention and readable notification colors. Existing Phase 4 loopback connection regressions cover registration and reconnect behavior. These tests do not establish physical multi-PC inference or a complete visual/accessibility acceptance review.

The local executable candidate, if successfully built, is isolated under `runtime/provider-design-candidate/`; it does not replace the installed provider, the existing installer download or the update feed. A versioned installer/release remains a separate operator-authorized step.

## Final evidence

Eight native widget/layout tests and 11 existing connection tests passed. Python compilation and scoped diff checks passed. PyInstaller 6.22.2 produced the isolated Windows candidate successfully. Final archive inspection confirms the new provider_views module, portal accent, and latest unsaved-sharing-choice handling are embedded. SHA-256: `0550b7ea7c06c9312759a76f0e83da673e60c714c39949d13a85e5780e983e59`. The EXE has not been launched, installed, published or distributed. Rendered screenshot acceptance and physical multi-PC inference were not performed.

## Dark mode, original EXE replacement and authorized feed publication — 2026-11-08

Added persisted Light/Dark/System appearance with native tuple-based colors. Theme changes do not reconstruct the form or discard unsaved values. Toolbar, status and notification colors adapt; the updater logic and connection protocol remain unchanged. The build is 2026.11.08-ui1. Nine native widget/theme/layout tests and 11 Phase 4 connection tests passed. Python compilation passed.

The operator explicitly approved publishing the update feed. The canonical and legacy EXEs, installer ZIPs and Inno Setup installer were rebuilt. The original D:\ComputeTorrent\ComputeTorrent_Seeder.exe was backed up and replaced with the matching build. Old artifacts and the prior manifest are retained under runtime/provider-release-backup-2026.11.08-ui1. The feed uses a versioned artifact and an atomic manifest replacement. Its HTTP manifest and full streamed download passed size and SHA-256 verification. Old-build and current-build version detection both passed. The existing portal download API still returns its configured 410 and was not re-enabled.

The actual frozen EXE launched with an isolated profile and exposed its 2026.11.08-ui1 native window. The test instance was closed and the replaced original-location EXE launched. Screenshot capture failed with FrameArrived timeout; activation and a fresh-window retry also failed with window capture timeout. Accordingly, rendered visual acceptance is still blocked by the capture environment; it is not recorded as passed. No multi-PC inference or automated installer installation/rollback was tested in this presentation update.

## Connection page visibility hotfix — 2026-11-08

The operator screenshot exposed a real regression: Connection was selected in the sidebar while Help obscured its form. CTkScrollableFrame grids an outer wrapper; tkraise on the inner frame did not raise that wrapper. Earlier tests checked widget existence and selected-name state, which did not prove page visibility.

The corrected shell gives each page its own host and maps only the selected host, retaining all child widgets and unsaved field values. A new native mapped-visibility regression failed on the old implementation and passes on the corrected code. Ten UI tests and 11 Phase 4 connection tests pass. The hotfix build is 2026.11.08-ui2. Source preview launched with the new window title; native activation/capture still timed out, so no screenshot-based visual pass is claimed.

## Provider navigation hotfix release — 2026-11-08

Fixed ui1 showing Help while Connection was selected. Only the selected page host is now mapped; hidden-page widgets retain unsaved values. A new real Tk visibility test failed against ui1 and passes for ui2. Ten UI and 11 connection tests passed. The 2026.11.08-ui2 EXE was rebuilt and its page-host closure inspected in the final archive. Original-location replacement preserved the settings file byte-for-byte before relaunch. Canonical/legacy EXEs and ZIPs were updated, and the previously authorized update feed now serves ui2; full HTTP download size/SHA-256 were verified. Prior artifacts remain backed up under runtime/provider-release-backup-2026.11.08-ui2. Native screenshot/activation timed out, so screenshot-based acceptance remains unverified.

Final ui2 packaging passed: Inno Setup compiled successfully; canonical/legacy EXE, setup and ZIP hashes match. The original-location native window reports 2026.11.08-ui2.

## Responsive overview — 2026-11-08

Workspace connection, resource snapshot and current assignment now share a responsive panel grid. At wide content widths they occupy one row; medium widths use two columns and narrow widths use one column. The layout updates placement and label wrapping without reconstructing live controls. The existing page-host navigation fix remains intact.

Eleven native UI tests pass, including repeated resizing at 1700, 1120, 960 and 800-pixel fixture window widths. At the wide fixture width, all three cards share a top coordinate, occupy distinct columns, and the task text is within the viewport. The same status widgets survive each reflow. Eleven existing connection regressions also pass. This is geometry/widget validation rather than a screenshot-based visual acceptance claim. Release target: 2026.11.08-ui3.

## Responsive provider overview release — 2026-11-08

2026.11.08-ui3 implements the requested side-by-side overview with three wide-screen columns, two medium-screen columns and a narrow-screen fallback. Eleven native layout/theme/navigation tests and eleven connection tests passed. Reflow preserves the live status widgets and keeps the wide-screen current-assignment text in view; card bounds were checked against the window. Before replacing the app, the release script checked for a current distributed assignment on this provider. Original-location replacement preserved settings byte-for-byte and relaunched the app. Canonical/legacy EXE and release metadata were updated and the previously authorized feed advanced to ui3. No updater or connection algorithm was changed.

Final packaging: Inno Setup ui3 compilation passed; mirrored artifacts match, ZIP metadata is ui3, and the HTTP update download passed SHA-256/size verification.

## Two-card header and full-width assignment — 2026-11-08

Per the operator’s revised layout, the overview uses two equal-width cards for connection/resources and a full-width current-assignment panel beneath them. Narrow windows retain a single-column fallback. Live widgets, controls, theme and connection behavior remain unchanged. Eleven native tests (including equal top widths, lower-panel columnspan/position/full width, responsive reflow and retained widgets) and eleven connection regressions pass. Target build is 2026.11.08-ui4.
