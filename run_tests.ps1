# Run all cohort test tiers from the repo root.
# Usage:
#   .\run_tests.ps1              # all tiers, verbose
#   .\run_tests.ps1 -Tier micro  # single tier
#   .\run_tests.ps1 -Tier large  # includes slow tests
#   .\run_tests.ps1 -Fast        # skip @pytest.mark.slow tests

param(
    [ValidateSet('all','micro','small','medium','large')]
    [string]$Tier = 'all',
    [switch]$Fast
)

$map = @{
    micro  = 'tests/test_micro.py'
    small  = 'tests/test_small.py'
    medium = 'tests/test_medium.py'
    large  = 'tests/test_large.py'
}

$target = if ($Tier -eq 'all') { 'tests/' } else { $map[$Tier] }
$slowFlag = if ($Fast) { '-m "not slow"' } else { '' }

Write-Host ""
Write-Host "  Photo Tool — Cohort Test Runner" -ForegroundColor Cyan
Write-Host "  Tier: $Tier   Target: $target" -ForegroundColor Gray
Write-Host ""

$cmd = "python -m pytest $target -v $slowFlag"
Write-Host "  $cmd" -ForegroundColor DarkGray
Write-Host ""

Invoke-Expression $cmd
