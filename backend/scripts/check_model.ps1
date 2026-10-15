# backend/scripts/check_model.ps1
#
# Health probe: ask the UF LiteLLM gateway which model actually serves the id
# this deployment requests, and report any substitution.
#
#   pwsh ./backend/scripts/check_model.ps1                 # reads ./.env
#   pwsh ./backend/scripts/check_model.ps1 -EnvFile ../.env
#
# Why PowerShell and not Python: on Windows dev machines behind a TLS-inspecting
# proxy, the venv's certifi bundle cannot chain the injected corporate CA and
# every openai-SDK call dies with CERTIFICATE_VERIFY_FAILED. PowerShell uses the
# Windows trust store, so it reaches the gateway where Python cannot. Inside the
# backend container there is no such problem — there, the same three checks are
# a few lines against app.core.llm.get_sync_llm_client().
#
# Exit codes: 0 = the requested id was served as-is, 1 = substituted or failed.
#
# What to read in the output:
#   served model                   - the LiteLLM *model group* that answered.
#   Llm_provider-X-Ms-Served-Model - the real upstream deployment/snapshot. This
#                                    is the one that moves when a model is
#                                    retired and the group is quietly re-backed;
#                                    the group name alone will not tell you.
#   X-Litellm-Attempted-Fallbacks  - non-zero means routing fell back for this
#                                    call rather than serving the primary.
param([string]$EnvFile = ".env")

if (-not (Test-Path $EnvFile)) {
    Write-Error "Env file not found: $EnvFile"
    exit 1
}

$settings = @{}
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $k, $v = $line -split "=", 2
        $settings[$k.Trim()] = $v.Trim().Trim('"').Trim("'")
    }
}

$key   = $settings["UF_OPENAI_API_KEY"]
$base  = $settings["UF_OPENAI_BASE_URL"]
$model = $settings["UF_OPENAI_API_MODEL"]

if (-not $base)  { $base = "https://api.ai.it.ufl.edu/v1" }
# Keep this fallback in step with DEFAULT_MODEL in backend/app/core/llm.py.
if (-not $model) { $model = "gpt-4.1" }

"configured base_url : $base"
"configured model    : $model"
if (-not $key) {
    Write-Error "No UF_OPENAI_API_KEY in $EnvFile - cannot probe the gateway."
    exit 1
}
""

$headers = @{ "Authorization" = "Bearer $key"; "Content-Type" = "application/json" }
$failed = $false

# 1. Is the configured id still in the catalog at all? -------------------------
"=== gateway catalog (GET /models) ==="
try {
    $catalog = Invoke-RestMethod -Uri "$base/models" -Headers $headers -Method GET `
        -TimeoutSec 30 -UseBasicParsing -ErrorAction Stop
    $ids = $catalog.data | ForEach-Object { $_.id } | Sort-Object
    "models served       : $($ids.Count)"
    "ids                 : $($ids -join ', ')"
    if ($ids -contains $model) {
        "configured present  : yes"
    } else {
        "configured present  : NO - '$model' is not in the catalog"
        $failed = $true
    }
} catch {
    "catalog call failed : $($_.Exception.Message)"
    $failed = $true
}
""

# 2. What answers when we actually ask for it? ---------------------------------
"=== completion probe (requested vs served) ==="
$body = @{
    model      = $model
    messages   = @(@{ role = "user"; content = "ping" })
    max_tokens = 1
} | ConvertTo-Json -Depth 5

try {
    $resp = Invoke-WebRequest -Uri "$base/chat/completions" -Headers $headers -Method POST `
        -Body $body -TimeoutSec 60 -UseBasicParsing -ErrorAction Stop
    $parsed = $resp.Content | ConvertFrom-Json

    "requested model     : $model"
    "served    model     : $($parsed.model)"
    if ($parsed.model -ne $model) {
        "SUBSTITUTED         : YES - the gateway remapped the configured id"
        $failed = $true
    } else {
        "SUBSTITUTED         : no"
    }

    "--- routing headers ---"
    foreach ($h in $resp.Headers.Keys) {
        if ($h -match "litellm-model|litellm-attempted|litellm-version|served-model|deprecat|sunset|warning") {
            "  $h : $($resp.Headers[$h])"
        }
    }
} catch {
    "probe failed        : $($_.Exception.Message)"
    if ($_.ErrorDetails.Message) { "detail              : $($_.ErrorDetails.Message)" }
    $failed = $true
}

""
if ($failed) {
    "RESULT: check the findings above before trusting the configured model."
    exit 1
}
"RESULT: '$model' is served as requested."
exit 0
