@echo off
setlocal

for %%I in ("%~dp0.") do set "ROOT=%%~fI"
for %%I in ("%ROOT%") do set "ROOT_DRIVE=%%~dI"
set "ENV_PATH=%ROOT%\.env"
set "PROJECT_VENV_PYTHON=%ROOT_DRIVE%\Telegram\.venv\Scripts\python.exe"
set "BUNDLE_PYTHON=%ROOT%\.venv\Scripts\python.exe"

if defined PYTHONPATH (
    set "PYTHONPATH=%ROOT%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%ROOT%"
)

set "ACTION=%~1"
if "%ACTION%"=="" goto :help_fail
shift

if /I "%ACTION%"=="help" goto :help_ok
if /I "%ACTION%"=="preview" goto :preview
if /I "%ACTION%"=="preview-offline" goto :preview_offline
if /I "%ACTION%"=="preview-golden" goto :preview_golden
if /I "%ACTION%"=="send-test" goto :send_test
if /I "%ACTION%"=="send-test-offline" goto :send_test_offline
if /I "%ACTION%"=="send-test-golden" goto :send_test_golden
if /I "%ACTION%"=="daily-check" goto :daily_check
if /I "%ACTION%"=="doctor" goto :doctor
if /I "%ACTION%"=="status" goto :doctor
if /I "%ACTION%"=="latest-artifacts" goto :latest_artifacts
if /I "%ACTION%"=="build-voice-package" goto :build_voice_package
if /I "%ACTION%"=="run" goto :run
if /I "%ACTION%"=="run-once" goto :run_once
if /I "%ACTION%"=="run-once-offline" goto :run_once_offline
if /I "%ACTION%"=="run-once-golden" goto :run_once_golden
if /I "%ACTION%"=="snapshot-offline" goto :snapshot_offline
if /I "%ACTION%"=="snapshot-golden" goto :snapshot_golden
if /I "%ACTION%"=="test-planner" goto :test_planner
if /I "%ACTION%"=="test-caption" goto :test_caption
if /I "%ACTION%"=="test-cards" goto :test_cards
if /I "%ACTION%"=="test-publish" goto :test_publish
if /I "%ACTION%"=="test-video" goto :test_video
if /I "%ACTION%"=="generate-captions" goto :generate_captions
if /I "%ACTION%"=="generate-captions-offline" goto :generate_captions_offline
if /I "%ACTION%"=="generate-captions-golden" goto :generate_captions_golden
if /I "%ACTION%"=="generate-cards" goto :generate_cards
if /I "%ACTION%"=="generate-cards-offline" goto :generate_cards_offline
if /I "%ACTION%"=="generate-cards-golden" goto :generate_cards_golden
if /I "%ACTION%"=="video-worker" goto :video_worker
if /I "%ACTION%"=="video-loop" goto :video_loop
if /I "%ACTION%"=="video-smoke" goto :video_smoke

echo Unknown action: %ACTION%
echo.
goto :help_fail

:preview
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli preview %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:preview_offline
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli preview --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:preview_golden
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli preview --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:send_test
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli send-test %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :execute_from_root

:send_test_offline
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli send-test --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :execute_from_root

:send_test_golden
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli send-test --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
goto :execute_from_root

:daily_check
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli daily-check %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:doctor
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli doctor %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:latest_artifacts
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli latest-artifacts %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:build_voice_package
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.operator_cli build-voice-package %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:run
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.main %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:run_once
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.main --once %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:run_once_offline
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.main --once --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:run_once_golden
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.main --once --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:snapshot_offline
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.main --capture-offline-snapshot %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:snapshot_golden
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m dealbot.main --capture-offline-snapshot --promote-offline-snapshot %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:test_planner
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m pytest -q tests/test_plan_queue_arch.py tests/test_lane_rebalance_arch.py %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:test_caption
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m pytest -q tests/test_caption_builder_arch.py tests/test_live_caption_validation_tool.py %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:test_cards
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m pytest -q tests/test_renderer_selector_arch.py tests/test_render_diagnostics_arch.py tests/test_yoto_card_engine_v4.py %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:test_publish
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py tests/test_publish_roundup_integration_arch.py tests/test_video_manifest_v2_arch.py %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:test_video
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m pytest -q video_generator/tests/test_scene_planner.py tests/test_pipeline.py %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:generate_captions
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" "%ROOT%tools\generate_yoto_v1_live_caption_validation.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:generate_captions_offline
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" "%ROOT%tools\generate_yoto_v1_live_caption_validation.py" --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:generate_captions_golden
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" "%ROOT%tools\generate_yoto_v1_live_caption_validation.py" --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:generate_cards
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" "%ROOT%tools\generate_yoto_v451_live_validation_pack.py" %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:generate_cards_offline
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" "%ROOT%tools\generate_yoto_v451_live_validation_pack.py" --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:generate_cards_golden
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" "%ROOT%tools\generate_yoto_v451_live_validation_pack.py" --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:video_worker
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m video_generator %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:video_loop
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m video_generator --loop %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:video_smoke
call :resolve_python
if errorlevel 1 exit /b 1
set YOTO_COMMAND="%YOTO_PYTHON%" -m video_generator --manifests-dir "%ROOT%video_generator\smoke_test\manifests" --videos-dir "%ROOT%output\videos\smoke" --temp-scenes-dir "%ROOT%temp\video_smoke_scenes" %1 %2 %3 %4 %5 %6 %7 %8 %9
call :execute_from_root
exit /b %ERRORLEVEL%

:resolve_python
if defined YOTO_PYTHON exit /b 0

if exist "%PROJECT_VENV_PYTHON%" (
    set "YOTO_PYTHON=%PROJECT_VENV_PYTHON%"
    exit /b 0
)

if exist "%BUNDLE_PYTHON%" (
    set "YOTO_PYTHON=%BUNDLE_PYTHON%"
    exit /b 0
)

echo [YOTO] No usable Python interpreter was found.
echo [YOTO] Checked:
echo [YOTO]   %PROJECT_VENV_PYTHON%
echo [YOTO]   %BUNDLE_PYTHON%
echo [YOTO] The launcher does not fall back to PATH Python.
echo [YOTO] Restore the project venv or bundle venv, then retry.
exit /b 1

:execute_from_root
if not defined YOTO_COMMAND (
    echo [YOTO] No command was prepared for execution.
    exit /b 1
)
pushd "%ROOT%" >nul
if errorlevel 1 (
    echo [YOTO] Failed to enter bundle root: %ROOT%
    exit /b 1
)
call %YOTO_COMMAND%
set "EXIT_CODE=%ERRORLEVEL%"
set "YOTO_COMMAND="
popd >nul
exit /b %EXIT_CODE%

:help_ok
echo YOTO operator commands
echo.
echo Safe operator commands ^(no Telegram publish^):
echo   yoto.bat doctor
echo   yoto.bat latest-artifacts
echo   yoto.bat preview
echo   yoto.bat preview-offline
echo   yoto.bat preview-golden
echo   yoto.bat daily-check
echo   yoto.bat snapshot-offline
echo   yoto.bat build-voice-package
echo   yoto.bat generate-captions [tool args]
echo   yoto.bat generate-captions-offline [tool args]
echo   yoto.bat generate-captions-golden [tool args]
echo   yoto.bat generate-cards [tool args]
echo   yoto.bat generate-cards-offline [tool args]
echo   yoto.bat generate-cards-golden [tool args]
echo   yoto.bat test-planner
echo   yoto.bat test-caption
echo   yoto.bat test-cards
echo   yoto.bat test-publish
echo   yoto.bat test-video
echo   yoto.bat video-smoke
echo.
echo Publish-capable or state-changing commands:
echo   yoto.bat send-test
echo   yoto.bat send-test-offline
echo   yoto.bat send-test-golden
echo   yoto.bat run-once
echo   yoto.bat run-once-offline
echo   yoto.bat run-once-golden
echo   yoto.bat run
echo   yoto.bat snapshot-golden
echo   yoto.bat video-loop
echo   yoto.bat video-worker
echo.
echo Daily operator surface:
echo   yoto.bat daily-check
echo   yoto.bat preview
echo   yoto.bat send-test
echo   yoto.bat build-voice-package
echo   yoto.bat latest-artifacts
echo   yoto.bat doctor
echo.
echo Offline-safe operator variants:
echo   yoto.bat preview-offline
echo   yoto.bat preview-golden
echo   yoto.bat send-test-offline
echo   yoto.bat send-test-golden
echo.
echo Existing pipeline and validation commands:
echo   yoto.bat snapshot-offline
echo   yoto.bat snapshot-golden
echo   yoto.bat run
echo   yoto.bat run-once
echo   yoto.bat run-once-offline
echo   yoto.bat run-once-golden
echo   yoto.bat test-planner
echo   yoto.bat test-caption
echo   yoto.bat test-cards
echo   yoto.bat test-publish
echo   yoto.bat test-video
echo   yoto.bat generate-captions [tool args]
echo   yoto.bat generate-captions-offline [tool args]
echo   yoto.bat generate-captions-golden [tool args]
echo   yoto.bat generate-cards [tool args]
echo   yoto.bat generate-cards-offline [tool args]
echo   yoto.bat generate-cards-golden [tool args]
echo   yoto.bat video-worker [video args]
echo   yoto.bat video-loop [video args]
echo   yoto.bat video-smoke [video args]
echo.
echo The launcher prefers %PROJECT_VENV_PYTHON%, then %BUNDLE_PYTHON%.
echo See docs\YOTO_COMMAND_INDEX.md for safe vs dangerous commands and docs\YOTO_OPERATOR_WORKFLOW.md for the daily workflow.
exit /b 0

:help_fail
call :help_ok
exit /b 1
