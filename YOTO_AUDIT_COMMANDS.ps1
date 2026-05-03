$ErrorActionPreference = 'Stop'

$Root = 'D:\Telegram_portable_bundle'
$Python = 'D:\Telegram\.venv\Scripts\python.exe'

if (-not (Test-Path $Root)) {
    throw "Repository root not found: $Root"
}

if (-not (Test-Path $Python)) {
    throw "Python not found: $Python"
}

Set-Location $Root

Write-Host '=== Repo state ==='
git rev-parse HEAD
git status --short

Write-Host ''
Write-Host '=== Rendering / provider flags ==='
Get-Content .env.example | Select-String 'CARD_RENDERER_MODE|CARD_RENDERER_FALLBACK_TO_LEGACY|IMAGE_PROVIDER_MODE|IMAGE_PIPELINE_VERSION|COMFYUI_ENABLED|COMFYUI_URL|COMFYUI_CHECKPOINT'

Write-Host ''
Write-Host '=== Static syntax check ==='
& $Python -m py_compile `
    dealbot\settings.py `
    infrastructure\render\cards\yoto_card_engine_v4.py `
    infrastructure\render\cards\image_providers\base.py `
    infrastructure\render\cards\image_providers\artwork_provider.py `
    infrastructure\render\cards\image_providers\placeholder_provider.py `
    infrastructure\render\cards\image_providers\comfyui_provider.py `
    infrastructure\render\cards\image_providers\resolver.py `
    infrastructure\render\cards\visual_decision_engine.py `
    infrastructure\render\cards\asset_source.py `
    infrastructure\render\cards\asset_sources\asset_cache.py `
    infrastructure\render\cards\asset_sources\official_asset_source.py `
    tools\ai_card_smoke.py `
    tests\test_ai_card_smoke.py `
    tests\test_visual_decision_engine.py `
    tests\test_official_asset_source.py `
    tests\test_asset_cache.py

Write-Host ''
Write-Host '=== Targeted tests ==='
& $Python -m pytest -q `
    tests/test_asset_cache.py `
    tests/test_official_asset_source.py `
    tests/test_visual_decision_engine.py `
    tests/test_ai_card_smoke.py

Write-Host ''
Write-Host '=== Smoke 1: provider selection / final_source=ai / resolver trace ==='
& $Python tools\ai_card_smoke.py current_env --runs 1 --debug-ai

$CurrentBatch = Get-ChildItem output\cards -Directory -Filter 'ai_card_smoke_batch_current_env_*' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($CurrentBatch) {
    $CurrentSummary = Get-Content (Join-Path $CurrentBatch.FullName 'batch_summary.json') -Raw | ConvertFrom-Json
    $CurrentResult = $CurrentSummary.results[0]

    Write-Host ''
    Write-Host '=== Current-env smoke summary ==='
    [pscustomobject]@{
        batch_manifest_path      = Join-Path $CurrentBatch.FullName 'batch_summary.json'
        review_cards_path        = $CurrentSummary.review_cards_path
        provider_attempted       = $CurrentResult.provider_attempted
        provider                 = $CurrentResult.provider
        final_source             = $CurrentResult.final_source
        ai_source_mode           = $CurrentResult.ai_source_mode
        selected_asset_source    = $CurrentResult.cover_decision_image_source_type
        actual_image_source_type = $CurrentResult.actual_image_source_type
        actual_image_path_or_url = $CurrentResult.actual_image_path_or_url
        output_path              = $CurrentResult.output_path
        manifest_path            = $CurrentResult.manifest_path
        decision_asset_used      = $CurrentResult.decision_asset_used
        decision_asset_reject    = $CurrentResult.decision_asset_reject_reason
        resolver_final_provider  = $CurrentResult.resolver_trace.final_selected_provider
        resolver_final_source    = $CurrentResult.resolver_trace.final_selected_source
        resolver_decision_reason = $CurrentResult.resolver_trace.final_decision_reason
    } | Format-List
}

Write-Host ''
Write-Host '=== Smoke 2: fallback behavior / official asset bridge / selected asset source ==='
& $Python tools\ai_card_smoke.py quality_reject --runs 1 --game-set minimal --debug-ai

$RejectBatch = Get-ChildItem output\cards -Directory -Filter 'ai_card_smoke_batch_quality_reject_*' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if ($RejectBatch) {
    $RejectSummary = Get-Content (Join-Path $RejectBatch.FullName 'batch_summary.json') -Raw | ConvertFrom-Json

    Write-Host ''
    Write-Host '=== Quality-reject batch summary ==='
    [pscustomobject]@{
        batch_manifest_path    = Join-Path $RejectBatch.FullName 'batch_summary.json'
        review_cards_path      = $RejectSummary.review_cards_path
        total_runs             = $RejectSummary.summary.total_runs
        ai_runtime_count       = $RejectSummary.summary.ai_runtime_count
        ai_fallback_count      = $RejectSummary.summary.ai_fallback_count
        ai_attempted_true_runs = $RejectSummary.summary.ai_attempted_true_runs
        fallback_used_runs     = $RejectSummary.summary.fallback_used_runs
        quality_reject_runs    = $RejectSummary.summary.quality_reject_runs
        errors                 = $RejectSummary.summary.errors
    } | Format-List

    $RejectSummary.results |
        Select-Object `
            game_slug,
            provider,
            final_source,
            cover_decision_image_source_type,
            actual_image_source_type,
            decision_asset_used,
            decision_asset_reject_reason,
            selected_asset_cache_status,
            output_path,
            manifest_path |
        Format-Table -AutoSize

    $FallbackRows = $RejectSummary.results | Where-Object { $_.final_source -eq 'fallback' }
    if ($FallbackRows) {
        Write-Host ''
        Write-Host '=== Fallback rows ==='
        $FallbackRows |
            Select-Object `
                game_slug,
                provider,
                final_source,
                fallback_used,
                fallback_reason,
                quality_reject_reason,
                actual_image_source_type,
                decision_asset_reject_reason,
                output_path,
                manifest_path |
            Format-Table -AutoSize
    }
}

Write-Host ''
Write-Host '=== Latest official asset cache files ==='
Get-ChildItem output\cards\official_asset_cache -Recurse -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20 FullName, Length, LastWriteTime |
    Format-Table -AutoSize

Write-Host ''
Write-Host '=== Latest smoke manifests ==='
Get-ChildItem output\cards -Recurse -File -Filter 'ai_card_smoke_manifest.json' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 10 FullName, LastWriteTime |
    Format-Table -AutoSize

Write-Host ''
Write-Host '=== Latest analytics / debug artifacts ==='
Get-ChildItem output\analytics -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20 FullName, LastWriteTime |
    Format-Table -AutoSize

Write-Host ''
Write-Host '=== Latest video manifests ==='
Get-ChildItem output\video_manifests -File -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 20 FullName, LastWriteTime |
    Format-Table -AutoSize
