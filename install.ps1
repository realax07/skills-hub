# skills-hub installer for Windows (PowerShell 5+ / pwsh).
# Без клона:
#   irm https://raw.githubusercontent.com/realax07/skills-hub/main/install.ps1 | iex
#   (запустит install с авто-поиском агентов; для опций — склонируй репо и вызови .\install.ps1)
# На Windows вместо симлинков создаются junction (не требуют прав администратора).
param(
  [Parameter(Position = 0)][string]$Command = "install",
  [Alias("a")][string]$Agent = "auto",
  [Alias("t")][string]$Topic = "",
  [Alias("s")][string]$Skill = "",
  [Alias("p")][string]$Project = "",
  [switch]$Copy,
  [switch]$Force,
  [Alias("n")][switch]$DryRun
)
$ErrorActionPreference = "Stop"
$RepoUrl = if ($env:SKILLS_HUB_REPO) { $env:SKILLS_HUB_REPO } else { "https://github.com/realax07/skills-hub.git" }
$HubHome = if ($env:SKILLS_HUB_HOME) { $env:SKILLS_HUB_HOME } else { Join-Path $HOME ".skills-hub" }
$Marker = ".skills-hub"

# --- bootstrap
$Repo = if ($PSScriptRoot) { $PSScriptRoot } else { "" }
if (-not $Repo -or -not (Test-Path (Join-Path $Repo "agents.conf"))) {
  if (Test-Path (Join-Path $HubHome ".git")) { git -C $HubHome pull --ff-only --quiet }
  else { git clone --quiet $RepoUrl $HubHome }
  & (Join-Path $HubHome "install.ps1") @PSBoundParameters
  return
}
$Repo = (Resolve-Path $Repo).Path
if ($Project) { $Project = (Resolve-Path $Project).Path }

function In-List($item, $list) { if (-not $list) { return $true }; return ($list -split ",") -contains $item }
function Expand-Home($p) { if ($p -eq "~") { return $HOME }; if ($p.StartsWith("~/")) { return Join-Path $HOME $p.Substring(2) }; return $p }
function Do-It([scriptblock]$b, [string]$desc) { if ($DryRun) { Write-Host "  [dry] $desc" } else { & $b } }

function Load-Agents {
  $map = [ordered]@{}
  foreach ($f in @("agents.conf", "agents.local.conf")) {
    $path = Join-Path $Repo $f
    if (-not (Test-Path $path)) { continue }
    foreach ($line in Get-Content $path) {
      $line = ($line -split "#")[0].Trim()
      if (-not $line) { continue }
      $c = $line -split "\s+"
      $layout = if ($c.Count -ge 4) { $c[3] } else { "flat" }
      $map[$c[0]] = [pscustomobject]@{ Id = $c[0]; User = (Expand-Home $c[1]); Project = $c[2]; Layout = $layout }
    }
  }
  return $map.Values
}
$AgentRows = Load-Agents

function Selected-Agents {
  $AgentRows | Where-Object {
    switch ($Agent) {
      "all" { $true }
      "auto" { Test-Path (Split-Path $_.User -Parent) }
      default { In-List $_.Id $Agent }
    }
  }
}

function All-Skills {
  Get-ChildItem -Path $Repo -Directory | Where-Object { $_.Name -notmatch "^[_.]" } | ForEach-Object {
    $topic = $_.Name
    $sk = Join-Path $_.FullName "skills"
    if (Test-Path $sk) {
      Get-ChildItem $sk -Directory | Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") } | ForEach-Object {
        [pscustomobject]@{ Topic = $topic; Skill = $_.Name; Dir = $_.FullName }
      }
    }
  }
}
function Selected-Skills { All-Skills | Where-Object { (In-List $_.Topic $Topic) -and (In-List $_.Skill $Skill) } }

function Root-For($a) {
  if ($Project) { if ($a.Project -eq "-") { return $null }; return Join-Path $Project $a.Project }
  return $a.User
}
function Dest-For($root, $a, $s) { if ($a.Layout -eq "category") { Join-Path (Join-Path $root $s.Topic) $s.Skill } else { Join-Path $root $s.Skill } }
function Is-Ours($d) {
  $item = Get-Item $d -Force -ErrorAction SilentlyContinue
  if (-not $item) { return $false }
  if ($item.LinkType) { return ([string]$item.Target).StartsWith($Repo) }
  return Test-Path (Join-Path $d $Marker)
}
function Remove-Dest($d) {
  $item = Get-Item $d -Force
  if ($item.LinkType) { $item.Delete() } else { Remove-Item $d -Recurse -Force }
}

function Cmd-List {
  $last = ""
  foreach ($s in All-Skills) {
    if ($s.Topic -ne $last) { Write-Host "$($s.Topic)/"; $last = $s.Topic }
    $desc = (Select-String -Path (Join-Path $s.Dir "SKILL.md") -Pattern "^description:\s*(.*)" | Select-Object -First 1).Matches.Groups[1].Value
    Write-Host ("  {0,-28} {1}" -f $s.Skill, $desc)
  }
}
function Cmd-Agents {
  foreach ($a in $AgentRows) {
    $found = if (Test-Path (Split-Path $a.User -Parent)) { "yes" } else { "-" }
    Write-Host ("{0,-10} {1,-6} {2,-40} {3}" -f $a.Id, $found, $a.User, $a.Project)
  }
}
function Cmd-Install {
  $dups = All-Skills | Group-Object Skill | Where-Object Count -gt 1
  if ($dups) { throw "Имена скиллов должны быть уникальны, дубли: $($dups.Name -join ', ')" }
  $agents = @(Selected-Agents); $skills = @(Selected-Skills)
  if (-not $agents) { throw "Агенты не найдены. Укажи явно: -Agent claude,codex или -Agent all" }
  if (-not $skills) { throw "Нет скиллов под фильтр (см. .\install.ps1 list)" }
  $n = 0
  foreach ($a in $agents) {
    $root = Root-For $a
    if (-not $root) { Write-Host "~ $($a.Id): project-скиллы не поддерживаются, пропуск"; continue }
    Write-Host "> $($a.Id) -> $root"
    foreach ($s in $skills) {
      $dest = Dest-For $root $a $s
      if (Get-Item $dest -Force -ErrorAction SilentlyContinue) {
        if (Is-Ours $dest) { Do-It { Remove-Dest $dest } "remove $dest" }
        elseif ($Force) { Do-It { Rename-Item $dest "$dest.bak.$([DateTimeOffset]::Now.ToUnixTimeSeconds())" } "backup $dest" }
        else { Write-Host "  ! $($s.Skill): $dest уже существует и не из skills-hub (используй -Force)"; continue }
      }
      Do-It { New-Item -ItemType Directory -Force -Path (Split-Path $dest -Parent) | Out-Null } "mkdir"
      if ($Copy) {
        Do-It { Copy-Item $s.Dir $dest -Recurse; Set-Content (Join-Path $dest $Marker) $Repo } "copy $($s.Dir) -> $dest"
        $mode = "copy"
      } else {
        Do-It { New-Item -ItemType Junction -Path $dest -Target $s.Dir | Out-Null } "junction $dest -> $($s.Dir)"
        $mode = "link"
      }
      Write-Host "  + $($s.Topic)/$($s.Skill) ($mode)"; $n++
    }
  }
  Write-Host "Готово: $n установок. Перезапусти агента, чтобы он подхватил скиллы."
}
function Cmd-Uninstall {
  if ($Agent -eq "auto") { $script:Agent = "all" }
  foreach ($a in Selected-Agents) {
    $root = Root-For $a; if (-not $root) { continue }
    foreach ($s in Selected-Skills) {
      $dest = Dest-For $root $a $s
      if (Is-Ours $dest) { Do-It { Remove-Dest $dest } "remove $dest"; Write-Host "  - $($a.Id): $($s.Topic)/$($s.Skill)" }
    }
  }
}
function Cmd-Status {
  if ($Agent -eq "auto") { $script:Agent = "all" }
  foreach ($a in Selected-Agents) {
    $root = Root-For $a; if (-not $root) { continue }
    $found = foreach ($s in Selected-Skills) { $d = Dest-For $root $a $s; if (Is-Ours $d) { $s.Skill } }
    if ($found) { Write-Host "$($a.Id): $($found -join ' ')" }
  }
}

switch ($Command) {
  "list" { Cmd-List }
  "agents" { Cmd-Agents }
  "install" { Cmd-Install }
  "uninstall" { Cmd-Uninstall }
  "status" { Cmd-Status }
  "update" { git -C $Repo pull --ff-only }
  default { Write-Host "Commands: list | agents | install | uninstall | status | update"; Write-Host "Options: -Agent -Topic -Skill -Project -Copy -Force -DryRun" }
}
