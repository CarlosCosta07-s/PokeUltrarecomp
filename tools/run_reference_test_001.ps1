[CmdletBinding()]
param(
    [switch]$AcceptThirdPartyCode,
    [switch]$KeepWorkspace,
    [string]$WorkspaceRoot = [System.IO.Path]::GetTempPath(),
    [string]$LogPath = (Join-Path ([System.IO.Path]::GetTempPath()) "PokeUltrarecomp-reference-test-001.log")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ReferenceRepository = "https://github.com/fearkov/3dsrecomp.git"
$ReferenceCommit = "c3f21f94ba50d688025febc8974ff348d471b587"
$MinimumRustVersion = [version]"1.88.0"
$TestCommand = "cargo test --locked --lib overrides::tests -- --nocapture"

$WorkDirectory = Join-Path $WorkspaceRoot ("PokeUltrarecomp-ReferenceTest001-" + [guid]::NewGuid().ToString("N"))
$SourceDirectory = Join-Path $WorkDirectory "source"
$CargoHome = Join-Path $WorkDirectory "cargo-home"
$CargoTarget = Join-Path $WorkDirectory "target"

$PreviousCargoHome = $env:CARGO_HOME
$PreviousCargoTarget = $env:CARGO_TARGET_DIR
$PreviousTerminalPrompt = $env:GIT_TERMINAL_PROMPT
$PreviousCargoColor = $env:CARGO_TERM_COLOR
$ExitCode = 0

function Restore-Environment {
    if ($null -eq $PreviousCargoHome) { Remove-Item Env:CARGO_HOME -ErrorAction SilentlyContinue }
    else { $env:CARGO_HOME = $PreviousCargoHome }

    if ($null -eq $PreviousCargoTarget) { Remove-Item Env:CARGO_TARGET_DIR -ErrorAction SilentlyContinue }
    else { $env:CARGO_TARGET_DIR = $PreviousCargoTarget }

    if ($null -eq $PreviousTerminalPrompt) { Remove-Item Env:GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue }
    else { $env:GIT_TERMINAL_PROMPT = $PreviousTerminalPrompt }

    if ($null -eq $PreviousCargoColor) { Remove-Item Env:CARGO_TERM_COLOR -ErrorAction SilentlyContinue }
    else { $env:CARGO_TERM_COLOR = $PreviousCargoColor }
}

try {
    foreach ($CommandName in @("git", "rustc", "cargo")) {
        if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
            throw "Required tool '$CommandName' was not found. Install it from its official source and reopen PowerShell."
        }
    }

    $GitVersionText = (& git --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not run Git."
    }

    $PowerShellVersionText = $PSVersionTable.PSVersion.ToString()
    $OSVersionText = [Environment]::OSVersion.VersionString

    $RustVersionText = (& rustc --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $RustVersionText -notmatch 'rustc\s+(\d+\.\d+\.\d+)') {
        throw "Could not determine the Rust compiler version."
    }
    $RustVersion = [version]$Matches[1]
    if ($RustVersion -lt $MinimumRustVersion) {
        throw "Rust $MinimumRustVersion or newer is required by the pinned reference package. Detected: $RustVersionText"
    }

    $CargoVersionText = (& cargo --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) {
        throw "Could not run Cargo."
    }

    New-Item -ItemType Directory -Path $WorkDirectory -Force | Out-Null
    $LogDirectory = Split-Path -Parent $LogPath
    if (-not [string]::IsNullOrWhiteSpace($LogDirectory)) {
        New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
    }

    @(
        "PokeUltrarecomp — reference test 001"
        "Reference repository: $ReferenceRepository"
        "Pinned commit: $ReferenceCommit"
        "Operating system: $OSVersionText"
        "PowerShell: $PowerShellVersionText"
        "Git: $GitVersionText"
        "Minimum Rust version: $MinimumRustVersion"
        "Detected Rust: $RustVersionText"
        "Detected Cargo: $CargoVersionText"
        "Test command: $TestCommand"
        "Game inputs: none"
        "Started (UTC): $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
        ""
    ) | Set-Content -LiteralPath $LogPath -Encoding utf8

    if (-not $AcceptThirdPartyCode) {
        throw "Safety stop: this runner fetches, compiles, and executes third-party source and dependency code. Review docs/REFERENCE_TEST_001.md first; run only as a non-admin user (preferably in a disposable VM/Sandbox), then explicitly pass -AcceptThirdPartyCode."
    }

    $env:GIT_TERMINAL_PROMPT = "0"
    $env:CARGO_TERM_COLOR = "never"
    $env:CARGO_HOME = $CargoHome
    $env:CARGO_TARGET_DIR = $CargoTarget

    Write-Host "Preparing an isolated temporary checkout of the pinned public source..."
    & git init --quiet $SourceDirectory
    if ($LASTEXITCODE -ne 0) { throw "git init failed." }

    & git -C $SourceDirectory remote add origin $ReferenceRepository
    if ($LASTEXITCODE -ne 0) { throw "Could not configure the temporary reference remote." }

    & git -C $SourceDirectory -c credential.helper= fetch --quiet --no-tags --no-recurse-submodules --depth 1 origin $ReferenceCommit
    if ($LASTEXITCODE -ne 0) { throw "Could not fetch the pinned reference commit. Check network access and retry." }

    & git -C $SourceDirectory checkout --quiet --detach FETCH_HEAD
    if ($LASTEXITCODE -ne 0) { throw "Could not check out the pinned reference commit." }

    $ActualCommit = (& git -C $SourceDirectory rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $ActualCommit -ne $ReferenceCommit) {
        throw "Reference revision mismatch. Expected $ReferenceCommit; got $ActualCommit."
    }

    $CargoManifest = Join-Path $SourceDirectory "Cargo.toml"
    $CargoLock = Join-Path $SourceDirectory "Cargo.lock"
    $OverrideSource = Join-Path $SourceDirectory "src/overrides.rs"
    foreach ($RequiredFile in @($CargoManifest, $CargoLock, $OverrideSource)) {
        if (-not (Test-Path -LiteralPath $RequiredFile -PathType Leaf)) {
            throw "The pinned source is missing an expected file: $(Split-Path -Leaf $RequiredFile)"
        }
    }

    $OverrideText = Get-Content -LiteralPath $OverrideSource -Raw
    foreach ($TestName in @("marks_are_found_outside_comments", "bad_marks_are_reported")) {
        if ($OverrideText -notmatch [regex]::Escape("fn $TestName")) {
            throw "Expected upstream unit test '$TestName' was not found in the pinned source."
        }
    }

    Add-Content -LiteralPath $LogPath -Encoding utf8 -Value @(
        "Checked out commit: $ActualCommit"
        "Source test names: marks_are_found_outside_comments; bad_marks_are_reported"
        "Workspace: isolated temporary directory"
        "Running tests..."
        ""
    )

    Write-Host "Pinned source verified: $ActualCommit"
    Write-Host "Running the two synthetic parser unit tests. No game files are used."

    Push-Location $SourceDirectory
    try {
        $TestOutput = & cargo test --locked --lib overrides::tests -- --nocapture 2>&1 |
            Tee-Object -FilePath $LogPath -Append
        $TestExitCode = $LASTEXITCODE
        $TestOutputText = ($TestOutput | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    }
    finally {
        Pop-Location
    }

    Add-Content -LiteralPath $LogPath -Encoding utf8 -Value @(
        ""
        "Cargo exit code: $TestExitCode"
        "Finished (UTC): $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
    )

    if ($TestExitCode -ne 0) {
        $ExitCode = $TestExitCode
        throw "The reference tests did not pass. Inspect the local log: $LogPath"
    }

    if ($TestOutputText -notmatch '(?m)^running 2 tests
    Write-Host "PASS: Cargo exited with code 0 for the pinned parser tests."
    Write-Host "Local log: $LogPath"
    Write-Host "This proves only these parser tests pass; it does not prove recompilation or game compatibility."
}
catch {
    if ($ExitCode -eq 0) { $ExitCode = 1 }
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    try {
        Add-Content -LiteralPath $LogPath -Encoding utf8 -Value @(
            ""
            "Runner error: $($_.Exception.Message)"
            "Finished (UTC): $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
        )
    } catch {
        # Preserve the primary test/runner error if a log cannot be written.
    }
}
finally {
    Restore-Environment

    if (-not $KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Remove-Item -LiteralPath $WorkDirectory -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Write-Host "Temporary workspace retained by request: $WorkDirectory"
    }
}

if ($ExitCode -ne 0) {
    exit $ExitCode
}
exit 0
 -or
        $TestOutputText -notmatch '(?m)^test overrides::tests::marks_are_found_outside_comments \.\.\. ok
    Write-Host "PASS: Cargo exited with code 0 for the pinned parser tests."
    Write-Host "Local log: $LogPath"
    Write-Host "This proves only these parser tests pass; it does not prove recompilation or game compatibility."
}
catch {
    if ($ExitCode -eq 0) { $ExitCode = 1 }
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    try {
        Add-Content -LiteralPath $LogPath -Encoding utf8 -Value @(
            ""
            "Runner error: $($_.Exception.Message)"
            "Finished (UTC): $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
        )
    } catch {
        # Preserve the primary test/runner error if a log cannot be written.
    }
}
finally {
    Restore-Environment

    if (-not $KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Remove-Item -LiteralPath $WorkDirectory -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Write-Host "Temporary workspace retained by request: $WorkDirectory"
    }
}

if ($ExitCode -ne 0) {
    exit $ExitCode
}
exit 0
 -or
        $TestOutputText -notmatch '(?m)^test overrides::tests::bad_marks_are_reported \.\.\. ok
    Write-Host "PASS: Cargo exited with code 0 for the pinned parser tests."
    Write-Host "Local log: $LogPath"
    Write-Host "This proves only these parser tests pass; it does not prove recompilation or game compatibility."
}
catch {
    if ($ExitCode -eq 0) { $ExitCode = 1 }
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    try {
        Add-Content -LiteralPath $LogPath -Encoding utf8 -Value @(
            ""
            "Runner error: $($_.Exception.Message)"
            "Finished (UTC): $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
        )
    } catch {
        # Preserve the primary test/runner error if a log cannot be written.
    }
}
finally {
    Restore-Environment

    if (-not $KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Remove-Item -LiteralPath $WorkDirectory -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Write-Host "Temporary workspace retained by request: $WorkDirectory"
    }
}

if ($ExitCode -ne 0) {
    exit $ExitCode
}
exit 0
 -or
        $TestOutputText -notmatch '(?m)^test result: ok\. 2 passed; 0 failed;') {
        $ExitCode = 1
        throw "Cargo exited successfully, but the output did not confirm exactly the two expected passing tests. Inspect the local log: $LogPath"
    }

    Write-Host ""
    Write-Host "PASS: Cargo exited with code 0 for the pinned parser tests."
    Write-Host "Local log: $LogPath"
    Write-Host "This proves only these parser tests pass; it does not prove recompilation or game compatibility."
}
catch {
    if ($ExitCode -eq 0) { $ExitCode = 1 }
    Write-Host ("ERROR: " + $_.Exception.Message) -ForegroundColor Red
    try {
        Add-Content -LiteralPath $LogPath -Encoding utf8 -Value @(
            ""
            "Runner error: $($_.Exception.Message)"
            "Finished (UTC): $([DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ'))"
        )
    } catch {
        # Preserve the primary test/runner error if a log cannot be written.
    }
}
finally {
    Restore-Environment

    if (-not $KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Remove-Item -LiteralPath $WorkDirectory -Recurse -Force -ErrorAction SilentlyContinue
    } elseif ($KeepWorkspace -and (Test-Path -LiteralPath $WorkDirectory)) {
        Write-Host "Temporary workspace retained by request: $WorkDirectory"
    }
}

if ($ExitCode -ne 0) {
    exit $ExitCode
}
exit 0
