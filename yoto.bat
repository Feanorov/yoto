@echo off
setlocal

set "ROOT=%~dp0"
if exist "%ROOT%.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
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
"%PYTHON%" -m dealbot.operator_cli preview %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:preview_offline
"%PYTHON%" -m dealbot.operator_cli preview --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:preview_golden
"%PYTHON%" -m dealbot.operator_cli preview --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:send_test
"%PYTHON%" -m dealbot.operator_cli send-test %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:send_test_offline
"%PYTHON%" -m dealbot.operator_cli send-test --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:send_test_golden
"%PYTHON%" -m dealbot.operator_cli send-test --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:daily_check
"%PYTHON%" -m dealbot.operator_cli daily-check %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:doctor
"%PYTHON%" -m dealbot.operator_cli doctor %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:latest_artifacts
"%PYTHON%" -m dealbot.operator_cli latest-artifacts %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:build_voice_package
"%PYTHON%" -m dealbot.operator_cli build-voice-package %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:run
"%PYTHON%" -m dealbot.main %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:run_once
"%PYTHON%" -m dealbot.main --once %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:run_once_offline
"%PYTHON%" -m dealbot.main --once --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:run_once_golden
"%PYTHON%" -m dealbot.main --once --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:snapshot_offline
"%PYTHON%" -m dealbot.main --capture-offline-snapshot %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:snapshot_golden
"%PYTHON%" -m dealbot.main --capture-offline-snapshot --promote-offline-snapshot %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:test_planner
"%PYTHON%" -m pytest -q tests/test_plan_queue_arch.py tests/test_lane_rebalance_arch.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:test_caption
"%PYTHON%" -m pytest -q tests/test_caption_builder_arch.py tests/test_live_caption_validation_tool.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:test_cards
"%PYTHON%" -m pytest -q tests/test_renderer_selector_arch.py tests/test_render_diagnostics_arch.py tests/test_yoto_card_engine_v4.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:test_publish
"%PYTHON%" -m pytest -q tests/test_publish_idempotency_arch.py tests/test_replay_outbox_arch.py tests/test_publish_roundup_integration_arch.py tests/test_video_manifest_v2_arch.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:test_video
"%PYTHON%" -m pytest -q video_generator/tests/test_scene_planner.py tests/test_pipeline.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:generate_captions
"%PYTHON%" tools\generate_yoto_v1_live_caption_validation.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:generate_captions_offline
"%PYTHON%" tools\generate_yoto_v1_live_caption_validation.py --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:generate_captions_golden
"%PYTHON%" tools\generate_yoto_v1_live_caption_validation.py --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:generate_cards
"%PYTHON%" tools\generate_yoto_v451_live_validation_pack.py %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:generate_cards_offline
"%PYTHON%" tools\generate_yoto_v451_live_validation_pack.py --offline-snapshot latest %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:generate_cards_golden
"%PYTHON%" tools\generate_yoto_v451_live_validation_pack.py --offline-snapshot golden %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:video_worker
"%PYTHON%" -m video_generator %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:video_loop
"%PYTHON%" -m video_generator --loop %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:video_smoke
"%PYTHON%" -m video_generator --manifests-dir "%ROOT%video_generator\smoke_test\manifests" --videos-dir "%ROOT%output\videos\smoke" --temp-scenes-dir "%ROOT%temp\video_smoke_scenes" %1 %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:help_ok
echo YOTO operator commands
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
echo See docs\YOTO_OPERATOR_WORKFLOW.md for the daily workflow, outputs, and blockers.
exit /b 0

:help_fail
call :help_ok
exit /b 1
