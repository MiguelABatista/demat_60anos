# Micro-interface de triagem manual (OBM -> PUC-Rio)
# Completamente isolada em triage_ui/; pode ser apagada depois sem afetar o projeto.

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$ErrorActionPreference = "Stop"

# Caminhos relativos à pasta triage_ui/
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
$InputCsv  = Join-Path $RepoRoot "data\puc\obm_university_puc_rio_candidates.csv"
$OutputCsv = Join-Path $RepoRoot "data\puc\obm_university_sem_evidencia_manual_triage.csv"

if (-not (Test-Path $InputCsv)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Arquivo de entrada não encontrado:`n$InputCsv",
        "Erro",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
    exit 1
}

# Detectar Firefox
function Find-Firefox {
    $candidates = @()

    foreach ($regPath in @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe"
    )) {
        try {
            if (Test-Path $regPath) {
                $val = (Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue).'(default)'
                if ($val) { $candidates += $val }
            }
        } catch {}
    }

    $candidates += @(
        "C:\Program Files\Mozilla Firefox\firefox.exe",
        "C:\Program Files (x86)\Mozilla Firefox\firefox.exe",
        (Join-Path $env:LOCALAPPDATA "Mozilla Firefox\firefox.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Mozilla Firefox\firefox.exe")
    )

    $cmd = Get-Command firefox.exe -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source) { $candidates += $cmd.Source }

    foreach ($path in ($candidates | Select-Object -Unique)) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }
    return $null
}

$script:FirefoxPath = Find-Firefox

function Detect-SourceType {
    param([string]$Url)
    if ([string]::IsNullOrWhiteSpace($Url)) { return "" }
    $u = $Url.Trim().ToLowerInvariant()
    if ($u -match 'lattes\.cnpq\.br|buscatextual\.cnpq\.br') { return "Lattes" }
    if ($u -match 'puc-rio\.br')                              { return "PUC-Rio" }
    if ($u -match 'escavador\.com')                           { return "Escavador" }
    if ($u -match 'linkedin\.com')                            { return "LinkedIn" }
    if ($u -match 'obm\.org\.br')                             { return "OBM" }
    if ($u -match 'impa\.br')                                 { return "IMPA" }
    if ($u -match 'ufrj\.br|ime\.eb\.br|fgv\.br|uff\.br|ita\.br|uerj\.br|usp\.br|unicamp\.br') { return "Site_IES" }
    return "Outro"
}

function Open-InFirefox {
    param([string]$Query)
    $encoded = [System.Uri]::EscapeDataString($Query)
    $url = "https://www.google.com/search?q=$encoded"
    try {
        if ($script:FirefoxPath -and (Test-Path $script:FirefoxPath)) {
            Start-Process -FilePath $script:FirefoxPath -ArgumentList @("-new-tab", $url) | Out-Null
        } else {
            Start-Process $url | Out-Null
        }
    } catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Não foi possível abrir o navegador:`n$($_.Exception.Message)",
            "Aviso",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    }
}

# Carregar somente os 95 SEM_EVIDENCIA do CSV original (somente leitura)
$allRows = @(Import-Csv -Path $InputCsv -Encoding UTF8)
$script:Candidates = @($allRows | Where-Object { $_.Classification -eq "SEM_EVIDENCIA" })

# Mapa de dicas úteis detectadas no CSV original
$script:Hints = @{
    "luize_durso" = "Dica: no CSV original existe 'Luíze Mello D'Urso Vianna' (2015, 2017, 2018) como PUC-Rio. Verifique se é a mesma pessoa."
}

# Carregar resultados já salvos anteriormente (para retomar de onde parou)
$script:SavedById = @{}
if (Test-Path $OutputCsv) {
    try {
        $existing = @(Import-Csv -Path $OutputCsv -Encoding UTF8)
        foreach ($r in $existing) {
            if ($r.OBM_Person_id) {
                $srcType = ""
                if ($r.PSObject.Properties.Name -contains "Source_Type" -and $r.Source_Type) {
                    $srcType = $r.Source_Type
                } else {
                    $srcType = Detect-SourceType -Url $r.Source_URL
                }
                $script:SavedById[$r.OBM_Person_id] = [PSCustomObject]@{
                    OBM_Person_id         = $r.OBM_Person_id
                    Person_canonical      = $r.Person_canonical
                    OBM_Years             = $r.OBM_Years
                    OBM_Cities            = $r.OBM_Cities
                    Institution           = $r.Institution
                    Classification        = $r.Classification
                    Temporal_Relation_OBM = $r.Temporal_Relation_OBM
                    Relevant_Years        = $r.Relevant_Years
                    Source_Type           = $srcType
                    Source_URL            = $r.Source_URL
                    Evidence_Excerpt      = $r.Evidence_Excerpt
                    Updated_At            = $r.Updated_At
                }
            }
        }
    } catch {
        [System.Windows.Forms.MessageBox]::Show(
            "Aviso ao ler arquivo salvo existente:`n$($_.Exception.Message)",
            "Aviso",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    }
}

function Save-AllToCsv {
    $ordered = New-Object System.Collections.ArrayList
    foreach ($c in $script:Candidates) {
        if ($script:SavedById.ContainsKey($c.OBM_Person_id)) {
            [void]$ordered.Add($script:SavedById[$c.OBM_Person_id])
        }
    }
    $tmpPath = "$OutputCsv.tmp"
    if ($ordered.Count -eq 0) {
        $header = '"OBM_Person_id","Person_canonical","OBM_Years","OBM_Cities","Institution","Classification","Temporal_Relation_OBM","Relevant_Years","Source_Type","Source_URL","Evidence_Excerpt","Updated_At"'
        [System.IO.File]::WriteAllText($tmpPath, $header + "`r`n", (New-Object System.Text.UTF8Encoding($true)))
    } else {
        $ordered | Export-Csv -Path $tmpPath -NoTypeInformation -Encoding UTF8
    }
    Move-Item -Path $tmpPath -Destination $OutputCsv -Force
}

# Estado de navegação
$script:VisibleIndices = @()
$script:CurrentPos = 0
$script:IsLoadingForm = $false
$script:SuppressAutoClass = $false

# ========================
# Construção da Interface
# ========================
$form = New-Object System.Windows.Forms.Form
$form.Text = "Triagem OBM -> PUC-Rio (95 SEM_EVIDENCIA)"
$form.Size = New-Object System.Drawing.Size(580, 740)
$form.MinimumSize = New-Object System.Drawing.Size(540, 700)
$form.StartPosition = "Manual"
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
$form.Location = New-Object System.Drawing.Point(($screen.Right - 600), ($screen.Top + 20))
$form.TopMost = $true
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$form.BackColor = [System.Drawing.Color]::FromArgb(248, 249, 252)
$form.KeyPreview = $true

# --- Barra superior: progresso e opções ---
$lblProgress = New-Object System.Windows.Forms.Label
$lblProgress.Location = New-Object System.Drawing.Point(16, 12)
$lblProgress.Size = New-Object System.Drawing.Size(400, 22)
$lblProgress.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
$lblProgress.ForeColor = [System.Drawing.Color]::FromArgb(30, 41, 59)
$form.Controls.Add($lblProgress)

$chkTopMost = New-Object System.Windows.Forms.CheckBox
$chkTopMost.Text = "Sempre no topo"
$chkTopMost.Checked = $true
$chkTopMost.AutoSize = $true
$chkTopMost.Location = New-Object System.Drawing.Point(432, 12)
$chkTopMost.Add_CheckedChanged({ $form.TopMost = $chkTopMost.Checked })
$form.Controls.Add($chkTopMost)

$progressBar = New-Object System.Windows.Forms.ProgressBar
$progressBar.Location = New-Object System.Drawing.Point(16, 38)
$progressBar.Size = New-Object System.Drawing.Size(532, 12)
$progressBar.Maximum = $script:Candidates.Count
$form.Controls.Add($progressBar)

# Filtro e navegação
$chkOnlyPending = New-Object System.Windows.Forms.CheckBox
$chkOnlyPending.Text = "Só pendentes"
$chkOnlyPending.Checked = $true
$chkOnlyPending.AutoSize = $true
$chkOnlyPending.Location = New-Object System.Drawing.Point(16, 58)
$form.Controls.Add($chkOnlyPending)

$cmbJump = New-Object System.Windows.Forms.ComboBox
$cmbJump.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$cmbJump.Location = New-Object System.Drawing.Point(128, 56)
$cmbJump.Size = New-Object System.Drawing.Size(262, 24)
$form.Controls.Add($cmbJump)

$btnPrev = New-Object System.Windows.Forms.Button
$btnPrev.Text = "< Ant."
$btnPrev.Location = New-Object System.Drawing.Point(398, 55)
$btnPrev.Size = New-Object System.Drawing.Size(72, 26)
$form.Controls.Add($btnPrev)

$btnNext = New-Object System.Windows.Forms.Button
$btnNext.Text = "Próx. >"
$btnNext.Location = New-Object System.Drawing.Point(476, 55)
$btnNext.Size = New-Object System.Drawing.Size(72, 26)
$form.Controls.Add($btnNext)

# --- Cartão do Candidato ---
$pnlCard = New-Object System.Windows.Forms.Panel
$pnlCard.Location = New-Object System.Drawing.Point(16, 90)
$pnlCard.Size = New-Object System.Drawing.Size(532, 108)
$pnlCard.BackColor = [System.Drawing.Color]::White
$pnlCard.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$form.Controls.Add($pnlCard)

$lblStatusBadge = New-Object System.Windows.Forms.Label
$lblStatusBadge.Location = New-Object System.Drawing.Point(412, 10)
$lblStatusBadge.Size = New-Object System.Drawing.Size(108, 22)
$lblStatusBadge.TextAlign = [System.Drawing.ContentAlignment]::MiddleCenter
$lblStatusBadge.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
$pnlCard.Controls.Add($lblStatusBadge)

$lblName = New-Object System.Windows.Forms.Label
$lblName.Location = New-Object System.Drawing.Point(12, 8)
$lblName.Size = New-Object System.Drawing.Size(394, 30)
$lblName.Font = New-Object System.Drawing.Font("Segoe UI", 13.5, [System.Drawing.FontStyle]::Bold)
$lblName.ForeColor = [System.Drawing.Color]::FromArgb(15, 23, 42)
$pnlCard.Controls.Add($lblName)

$lblMeta = New-Object System.Windows.Forms.Label
$lblMeta.Location = New-Object System.Drawing.Point(14, 42)
$lblMeta.Size = New-Object System.Drawing.Size(504, 22)
$lblMeta.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$lblMeta.ForeColor = [System.Drawing.Color]::FromArgb(71, 85, 105)
$pnlCard.Controls.Add($lblMeta)

$lblHint = New-Object System.Windows.Forms.Label
$lblHint.Location = New-Object System.Drawing.Point(14, 65)
$lblHint.Size = New-Object System.Drawing.Size(504, 36)
$lblHint.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Italic)
$lblHint.ForeColor = [System.Drawing.Color]::FromArgb(180, 83, 9)
$pnlCard.Controls.Add($lblHint)

# --- Seção Firefox / Busca ---
$grpSearch = New-Object System.Windows.Forms.GroupBox
$grpSearch.Text = "Busca no Firefox"
$grpSearch.Location = New-Object System.Drawing.Point(16, 206)
$grpSearch.Size = New-Object System.Drawing.Size(532, 100)
$form.Controls.Add($grpSearch)

$chkAutoOpen = New-Object System.Windows.Forms.CheckBox
$chkAutoOpen.Text = "Abrir Firefox automaticamente ao avançar"
$chkAutoOpen.Checked = $true
$chkAutoOpen.AutoSize = $true
$chkAutoOpen.Location = New-Object System.Drawing.Point(12, 22)
$grpSearch.Controls.Add($chkAutoOpen)

$lblBrowser = New-Object System.Windows.Forms.Label
$lblBrowser.Location = New-Object System.Drawing.Point(312, 23)
$lblBrowser.Size = New-Object System.Drawing.Size(210, 20)
$lblBrowser.TextAlign = [System.Drawing.ContentAlignment]::MiddleRight
$lblBrowser.Font = New-Object System.Drawing.Font("Segoe UI", 8.5)
$grpSearch.Controls.Add($lblBrowser)

function Update-BrowserLabel {
    if ($script:FirefoxPath -and (Test-Path $script:FirefoxPath)) {
        $lblBrowser.Text = "Firefox: detectado"
        $lblBrowser.ForeColor = [System.Drawing.Color]::FromArgb(22, 101, 52)
    } else {
        $lblBrowser.Text = "Firefox não achado (usando padrão)"
        $lblBrowser.ForeColor = [System.Drawing.Color]::FromArgb(180, 83, 9)
    }
}
Update-BrowserLabel

$btnSearchMain = New-Object System.Windows.Forms.Button
$btnSearchMain.Text = "Google: Nome (F2)"
$btnSearchMain.Location = New-Object System.Drawing.Point(12, 50)
$btnSearchMain.Size = New-Object System.Drawing.Size(148, 36)
$btnSearchMain.BackColor = [System.Drawing.Color]::FromArgb(37, 99, 235)
$btnSearchMain.ForeColor = [System.Drawing.Color]::White
$btnSearchMain.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnSearchMain.Font = New-Object System.Drawing.Font("Segoe UI", 9.5, [System.Drawing.FontStyle]::Bold)
$grpSearch.Controls.Add($btnSearchMain)

$btnSearchPuc = New-Object System.Windows.Forms.Button
$btnSearchPuc.Text = "+ PUC-Rio (F3)"
$btnSearchPuc.Location = New-Object System.Drawing.Point(168, 50)
$btnSearchPuc.Size = New-Object System.Drawing.Size(112, 36)
$grpSearch.Controls.Add($btnSearchPuc)

$btnSearchAcad = New-Object System.Windows.Forms.Button
$btnSearchAcad.Text = "+ Lattes/Escav."
$btnSearchAcad.Location = New-Object System.Drawing.Point(288, 50)
$btnSearchAcad.Size = New-Object System.Drawing.Size(120, 36)
$grpSearch.Controls.Add($btnSearchAcad)

$btnPickFirefox = New-Object System.Windows.Forms.Button
$btnPickFirefox.Text = "firefox.exe..."
$btnPickFirefox.Location = New-Object System.Drawing.Point(416, 50)
$btnPickFirefox.Size = New-Object System.Drawing.Size(104, 36)
$grpSearch.Controls.Add($btnPickFirefox)

# --- Seção Resposta Rápida + Fonte ---
$grpAnswer = New-Object System.Windows.Forms.GroupBox
$grpAnswer.Text = "Registrar faculdade e fonte"
$grpAnswer.Location = New-Object System.Drawing.Point(16, 314)
$grpAnswer.Size = New-Object System.Drawing.Size(532, 318)
$form.Controls.Add($grpAnswer)

# Atalhos de 1 clique
$quickItems = @(
    @{ Label = "PUC-Rio"; Inst = "PUC-Rio"; Class = "CONFIRMADO_PUC"; Color = [System.Drawing.Color]::FromArgb(22, 163, 74); Fg = [System.Drawing.Color]::White },
    @{ Label = "UFRJ";    Inst = "UFRJ";    Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black },
    @{ Label = "IME";     Inst = "IME";     Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black },
    @{ Label = "FGV";     Inst = "FGV";     Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black },
    @{ Label = "UFF";     Inst = "UFF";     Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black },
    @{ Label = "ITA";     Inst = "ITA";     Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black },
    @{ Label = "IMPA";    Inst = "IMPA";    Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black },
    @{ Label = "UERJ";    Inst = "UERJ";    Class = "OUTRA_INSTITUICAO"; Color = [System.Drawing.Color]::White; Fg = [System.Drawing.Color]::Black }
)

$qx = 12
foreach ($item in $quickItems) {
    $b = New-Object System.Windows.Forms.Button
    $b.Text = $item.Label
    $w = if ($item.Label -eq "PUC-Rio") { 76 } else { 58 }
    $b.Location = New-Object System.Drawing.Point($qx, 22)
    $b.Size = New-Object System.Drawing.Size($w, 28)
    $b.BackColor = $item.Color
    $b.ForeColor = $item.Fg
    if ($item.Label -eq "PUC-Rio") {
        $b.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
        $b.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    }
    $b.Tag = $item
    $b.Add_Click({
        param($sender, $e)
        $meta = $sender.Tag
        $script:SuppressAutoClass = $true
        $txtInst.Text = $meta.Inst
        $cmbClass.SelectedItem = $meta.Class
        if ($cmbPeriod.SelectedItem -eq "NAO_APLICAVEL") {
            $cmbPeriod.SelectedItem = "CONTEMPORANEA_OBM"
        }
        $script:SuppressAutoClass = $false
        if ([string]::IsNullOrWhiteSpace($txtUrl.Text)) {
            $txtUrl.Focus()
        } else {
            $txtInst.Focus()
            $txtInst.SelectionStart = $txtInst.Text.Length
        }
    })
    $grpAnswer.Controls.Add($b)
    $qx += ($w + 4)
}

# Segunda linha de atalhos especiais
$btnQuickPossivel = New-Object System.Windows.Forms.Button
$btnQuickPossivel.Text = "Possível PUC"
$btnQuickPossivel.Location = New-Object System.Drawing.Point(12, 56)
$btnQuickPossivel.Size = New-Object System.Drawing.Size(115, 26)
$btnQuickPossivel.Add_Click({
    $script:SuppressAutoClass = $true
    if ([string]::IsNullOrWhiteSpace($txtInst.Text)) { $txtInst.Text = "PUC-Rio?" }
    $cmbClass.SelectedItem = "POSSIVEL"
    $cmbPeriod.SelectedItem = "INCONCLUSIVO"
    $script:SuppressAutoClass = $false
    $txtUrl.Focus()
})
$grpAnswer.Controls.Add($btnQuickPossivel)

$btnQuickInc = New-Object System.Windows.Forms.Button
$btnQuickInc.Text = "Inconclusivo / Homônimo"
$btnQuickInc.Location = New-Object System.Drawing.Point(133, 56)
$btnQuickInc.Size = New-Object System.Drawing.Size(168, 26)
$btnQuickInc.Add_Click({
    $script:SuppressAutoClass = $true
    $cmbClass.SelectedItem = "SEM_EVIDENCIA"
    $cmbPeriod.SelectedItem = "INCONCLUSIVO"
    if ([string]::IsNullOrWhiteSpace($txtNotes.Text)) { $txtNotes.Text = "Inconclusivo / homônimo" }
    $script:SuppressAutoClass = $false
    $txtNotes.Focus()
})
$grpAnswer.Controls.Add($btnQuickInc)

$btnQuickSem = New-Object System.Windows.Forms.Button
$btnQuickSem.Text = "Sem evidência"
$btnQuickSem.Location = New-Object System.Drawing.Point(307, 56)
$btnQuickSem.Size = New-Object System.Drawing.Size(115, 26)
$btnQuickSem.Add_Click({
    $script:SuppressAutoClass = $true
    $txtInst.Text = ""
    $txtUrl.Text = ""
    $cmbSourceType.SelectedItem = ""
    $cmbClass.SelectedItem = "SEM_EVIDENCIA"
    $cmbPeriod.SelectedItem = "NAO_APLICAVEL"
    $script:SuppressAutoClass = $false
    $btnSaveNext.Focus()
})
$grpAnswer.Controls.Add($btnQuickSem)

# Campo 1: Faculdade / Instituição
$lblInst = New-Object System.Windows.Forms.Label
$lblInst.Text = "1. Faculdade / Instituição:"
$lblInst.Location = New-Object System.Drawing.Point(12, 92)
$lblInst.Size = New-Object System.Drawing.Size(260, 19)
$lblInst.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$grpAnswer.Controls.Add($lblInst)

$txtInst = New-Object System.Windows.Forms.TextBox
$txtInst.Location = New-Object System.Drawing.Point(12, 112)
$txtInst.Size = New-Object System.Drawing.Size(506, 26)
$txtInst.Font = New-Object System.Drawing.Font("Segoe UI", 10.5)
$grpAnswer.Controls.Add($txtInst)

# Campo 2: Fonte (URL + Tipo auto-detectado + Colar F4)
$lblUrl = New-Object System.Windows.Forms.Label
$lblUrl.Text = "2. URL da fonte (Ctrl+V ou F4 para colar do navegador):"
$lblUrl.Location = New-Object System.Drawing.Point(12, 145)
$lblUrl.Size = New-Object System.Drawing.Size(340, 19)
$lblUrl.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
$grpAnswer.Controls.Add($lblUrl)

$chkRequireUrl = New-Object System.Windows.Forms.CheckBox
$chkRequireUrl.Text = "Exigir fonte"
$chkRequireUrl.Checked = $true
$chkRequireUrl.AutoSize = $true
$chkRequireUrl.Location = New-Object System.Drawing.Point(424, 144)
$grpAnswer.Controls.Add($chkRequireUrl)

$txtUrl = New-Object System.Windows.Forms.TextBox
$txtUrl.Location = New-Object System.Drawing.Point(12, 166)
$txtUrl.Size = New-Object System.Drawing.Size(316, 25)
$txtUrl.Font = New-Object System.Drawing.Font("Segoe UI", 9.5)
$grpAnswer.Controls.Add($txtUrl)

$btnPasteUrl = New-Object System.Windows.Forms.Button
$btnPasteUrl.Text = "Colar (F4)"
$btnPasteUrl.Location = New-Object System.Drawing.Point(334, 165)
$btnPasteUrl.Size = New-Object System.Drawing.Size(80, 26)
$btnPasteUrl.BackColor = [System.Drawing.Color]::FromArgb(224, 231, 255)
$btnPasteUrl.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$grpAnswer.Controls.Add($btnPasteUrl)

$cmbSourceType = New-Object System.Windows.Forms.ComboBox
$cmbSourceType.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$cmbSourceType.Location = New-Object System.Drawing.Point(420, 166)
$cmbSourceType.Size = New-Object System.Drawing.Size(98, 25)
[void]$cmbSourceType.Items.AddRange(@("", "Lattes", "PUC-Rio", "Escavador", "LinkedIn", "OBM", "IMPA", "Site_IES", "Outro"))
$grpAnswer.Controls.Add($cmbSourceType)

# Aviso inline de validação (ex: faltou URL)
$lblValidation = New-Object System.Windows.Forms.Label
$lblValidation.Location = New-Object System.Drawing.Point(12, 194)
$lblValidation.Size = New-Object System.Drawing.Size(506, 18)
$lblValidation.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
$lblValidation.ForeColor = [System.Drawing.Color]::FromArgb(185, 28, 28)
$lblValidation.Text = ""
$grpAnswer.Controls.Add($lblValidation)

# Classificação, Período e Anos
$lblClass = New-Object System.Windows.Forms.Label
$lblClass.Text = "Classificação:"
$lblClass.Location = New-Object System.Drawing.Point(12, 214)
$lblClass.Size = New-Object System.Drawing.Size(170, 18)
$grpAnswer.Controls.Add($lblClass)

$cmbClass = New-Object System.Windows.Forms.ComboBox
$cmbClass.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$cmbClass.Location = New-Object System.Drawing.Point(12, 233)
$cmbClass.Size = New-Object System.Drawing.Size(175, 24)
[void]$cmbClass.Items.AddRange(@("CONFIRMADO_PUC", "POSSIVEL", "OUTRA_INSTITUICAO", "SEM_EVIDENCIA"))
$grpAnswer.Controls.Add($cmbClass)

$lblPeriod = New-Object System.Windows.Forms.Label
$lblPeriod.Text = "Vínculo / OBM:"
$lblPeriod.Location = New-Object System.Drawing.Point(198, 214)
$lblPeriod.Size = New-Object System.Drawing.Size(165, 18)
$grpAnswer.Controls.Add($lblPeriod)

$cmbPeriod = New-Object System.Windows.Forms.ComboBox
$cmbPeriod.DropDownStyle = [System.Windows.Forms.ComboBoxStyle]::DropDownList
$cmbPeriod.Location = New-Object System.Drawing.Point(198, 233)
$cmbPeriod.Size = New-Object System.Drawing.Size(170, 24)
[void]$cmbPeriod.Items.AddRange(@("CONTEMPORANEA_OBM", "OUTRO_PERIODO", "INCONCLUSIVO", "NAO_APLICAVEL"))
$grpAnswer.Controls.Add($cmbPeriod)

$lblYears = New-Object System.Windows.Forms.Label
$lblYears.Text = "Anos (opcional):"
$lblYears.Location = New-Object System.Drawing.Point(378, 214)
$lblYears.Size = New-Object System.Drawing.Size(140, 18)
$grpAnswer.Controls.Add($lblYears)

$txtYears = New-Object System.Windows.Forms.TextBox
$txtYears.Location = New-Object System.Drawing.Point(378, 233)
$txtYears.Size = New-Object System.Drawing.Size(140, 24)
$grpAnswer.Controls.Add($txtYears)

# Trecho / Observação
$lblNotes = New-Object System.Windows.Forms.Label
$lblNotes.Text = "Trecho / Obs.:"
$lblNotes.Location = New-Object System.Drawing.Point(12, 272)
$lblNotes.Size = New-Object System.Drawing.Size(96, 20)
$grpAnswer.Controls.Add($lblNotes)

$txtNotes = New-Object System.Windows.Forms.TextBox
$txtNotes.Location = New-Object System.Drawing.Point(110, 270)
$txtNotes.Size = New-Object System.Drawing.Size(408, 24)
$grpAnswer.Controls.Add($txtNotes)

# Auto-detectar tipo da fonte quando colar/editar URL
$txtUrl.Add_TextChanged({
    $lblValidation.Text = ""
    if ($script:SuppressAutoClass) { return }
    $detected = Detect-SourceType -Url $txtUrl.Text
    if ($cmbSourceType.Items.Contains($detected)) {
        $cmbSourceType.SelectedItem = $detected
    }
})

function Paste-UrlFromClipboard {
    try {
        $clip = [System.Windows.Forms.Clipboard]::GetText()
        if ($clip) {
            $txtUrl.Text = $clip.Trim()
            $lblValidation.Text = ""
            $txtUrl.Focus()
            $txtUrl.SelectionStart = $txtUrl.Text.Length
        }
    } catch {}
}

$btnPasteUrl.Add_Click({ Paste-UrlFromClipboard })

# Auto-classificação ao digitar no campo Faculdade
$txtInst.Add_TextChanged({
    $lblValidation.Text = ""
    if ($script:SuppressAutoClass) { return }
    $val = $txtInst.Text.Trim()
    if ([string]::IsNullOrWhiteSpace($val)) {
        $cmbClass.SelectedItem = "SEM_EVIDENCIA"
        $cmbPeriod.SelectedItem = "NAO_APLICAVEL"
    } elseif ($val -match '(?i)\bpuc\b|puc-rio|pontif[ií]cia') {
        $cmbClass.SelectedItem = "CONFIRMADO_PUC"
        if ($cmbPeriod.SelectedItem -eq "NAO_APLICAVEL") {
            $cmbPeriod.SelectedItem = "CONTEMPORANEA_OBM"
        }
    } else {
        $cmbClass.SelectedItem = "OUTRA_INSTITUICAO"
        if ($cmbPeriod.SelectedItem -eq "NAO_APLICAVEL") {
            $cmbPeriod.SelectedItem = "CONTEMPORANEA_OBM"
        }
    }
})

# --- Barra de ações inferior ---
$btnSkip = New-Object System.Windows.Forms.Button
$btnSkip.Text = "Pular (Esc)"
$btnSkip.Location = New-Object System.Drawing.Point(16, 644)
$btnSkip.Size = New-Object System.Drawing.Size(118, 42)
$form.Controls.Add($btnSkip)

$btnSaveOnly = New-Object System.Windows.Forms.Button
$btnSaveOnly.Text = "Só salvar"
$btnSaveOnly.Location = New-Object System.Drawing.Point(142, 644)
$btnSaveOnly.Size = New-Object System.Drawing.Size(110, 42)
$form.Controls.Add($btnSaveOnly)

$btnSaveNext = New-Object System.Windows.Forms.Button
$btnSaveNext.Text = "Salvar e Próximo (Enter)"
$btnSaveNext.Location = New-Object System.Drawing.Point(260, 644)
$btnSaveNext.Size = New-Object System.Drawing.Size(288, 42)
$btnSaveNext.BackColor = [System.Drawing.Color]::FromArgb(22, 163, 74)
$btnSaveNext.ForeColor = [System.Drawing.Color]::White
$btnSaveNext.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$btnSaveNext.Font = New-Object System.Drawing.Font("Segoe UI", 10.5, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($btnSaveNext)

# ========================
# Lógica de Navegação
# ========================
function Get-CurrentCandidate {
    if ($script:VisibleIndices.Count -eq 0) { return $null }
    if ($script:CurrentPos -lt 0) { $script:CurrentPos = 0 }
    if ($script:CurrentPos -ge $script:VisibleIndices.Count) { $script:CurrentPos = $script:VisibleIndices.Count - 1 }
    return $script:Candidates[$script:VisibleIndices[$script:CurrentPos]]
}

function Update-ProgressUI {
    $total = $script:Candidates.Count
    $done = $script:SavedById.Count
    $pucCount = 0
    $posCount = 0
    $otherCount = 0
    foreach ($v in $script:SavedById.Values) {
        switch ($v.Classification) {
            "CONFIRMADO_PUC"    { $pucCount++ }
            "POSSIVEL"          { $posCount++ }
            "OUTRA_INSTITUICAO" { $otherCount++ }
        }
    }
    $lblProgress.Text = "Salvos: $done/$total  |  PUC: $pucCount  |  Possível: $posCount  |  Outra: $otherCount"
    $progressBar.Value = [Math]::Min($done, $total)
}

function Rebuild-VisibleList {
    param([string]$KeepPersonId = $null)
    $script:IsLoadingForm = $true
    $list = New-Object System.Collections.ArrayList
    for ($i = 0; $i -lt $script:Candidates.Count; $i++) {
        $c = $script:Candidates[$i]
        $isSaved = $script:SavedById.ContainsKey($c.OBM_Person_id)
        if (-not $chkOnlyPending.Checked -or -not $isSaved) {
            [void]$list.Add($i)
        }
    }
    $script:VisibleIndices = @($list.ToArray())

    $cmbJump.Items.Clear()
    $targetPos = 0
    for ($pos = 0; $pos -lt $script:VisibleIndices.Count; $pos++) {
        $c = $script:Candidates[$script:VisibleIndices[$pos]]
        $mark = if ($script:SavedById.ContainsKey($c.OBM_Person_id)) { "[OK] " } else { "" }
        [void]$cmbJump.Items.Add("$($pos + 1). $mark$($c.Person_canonical)")
        if ($KeepPersonId -and $c.OBM_Person_id -eq $KeepPersonId) {
            $targetPos = $pos
        }
    }

    if ($script:VisibleIndices.Count -eq 0) {
        $script:CurrentPos = 0
    } elseif ($KeepPersonId) {
        $script:CurrentPos = $targetPos
    } elseif ($script:CurrentPos -ge $script:VisibleIndices.Count) {
        $script:CurrentPos = $script:VisibleIndices.Count - 1
    }

    if ($cmbJump.Items.Count -gt 0) {
        $cmbJump.SelectedIndex = $script:CurrentPos
    }
    $script:IsLoadingForm = $false
}

function Load-CurrentCandidateUI {
    param([bool]$AutoOpenBrowser = $false)
    Update-ProgressUI
    $lblValidation.Text = ""
    $c = Get-CurrentCandidate

    if ($null -eq $c) {
        $lblName.Text = "Todos os 95 candidatos concluídos!"
        $lblMeta.Text = "Arquivo salvo em: data\puc\obm_university_sem_evidencia_manual_triage.csv"
        $lblHint.Text = "Desmarque 'Só pendentes' acima se quiser revisar ou editar alguém."
        $lblStatusBadge.Text = "CONCLUÍDO"
        $lblStatusBadge.BackColor = [System.Drawing.Color]::FromArgb(220, 252, 231)
        $lblStatusBadge.ForeColor = [System.Drawing.Color]::FromArgb(22, 101, 52)
        $grpAnswer.Enabled = $false
        $btnSaveNext.Enabled = $false
        $btnSaveOnly.Enabled = $false
        $btnSkip.Enabled = $false
        return
    }

    $grpAnswer.Enabled = $true
    $btnSaveNext.Enabled = $true
    $btnSaveOnly.Enabled = $true
    $btnSkip.Enabled = $true

    $script:IsLoadingForm = $true
    if ($cmbJump.Items.Count -gt $script:CurrentPos) {
        $cmbJump.SelectedIndex = $script:CurrentPos
    }
    $script:IsLoadingForm = $false

    $lblName.Text = $c.Person_canonical
    $lblMeta.Text = "OBM: $($c.OBM_Years)   |   Cidade: $($c.OBM_Cities)   |   Item $($script:CurrentPos + 1) de $($script:VisibleIndices.Count)"

    if ($script:Hints.ContainsKey($c.OBM_Person_id)) {
        $lblHint.Text = $script:Hints[$c.OBM_Person_id]
    } else {
        $lblHint.Text = "ID: $($c.OBM_Person_id)"
    }

    $script:SuppressAutoClass = $true
    if ($script:SavedById.ContainsKey($c.OBM_Person_id)) {
        $saved = $script:SavedById[$c.OBM_Person_id]
        $txtInst.Text = $saved.Institution
        $cmbClass.SelectedItem = if ($saved.Classification) { $saved.Classification } else { "SEM_EVIDENCIA" }
        $cmbPeriod.SelectedItem = if ($saved.Temporal_Relation_OBM) { $saved.Temporal_Relation_OBM } else { "NAO_APLICAVEL" }
        $txtYears.Text = $saved.Relevant_Years
        $txtUrl.Text = $saved.Source_URL
        $st = if ($saved.Source_Type) { $saved.Source_Type } else { Detect-SourceType -Url $saved.Source_URL }
        if ($cmbSourceType.Items.Contains($st)) { $cmbSourceType.SelectedItem = $st } else { $cmbSourceType.SelectedItem = "" }
        $txtNotes.Text = $saved.Evidence_Excerpt

        $lblStatusBadge.Text = "SALVO"
        $lblStatusBadge.BackColor = [System.Drawing.Color]::FromArgb(220, 252, 231)
        $lblStatusBadge.ForeColor = [System.Drawing.Color]::FromArgb(22, 101, 52)
    } else {
        $txtInst.Text = ""
        $cmbClass.SelectedItem = "SEM_EVIDENCIA"
        $cmbPeriod.SelectedItem = "NAO_APLICAVEL"
        $txtYears.Text = ""
        $txtUrl.Text = ""
        $cmbSourceType.SelectedItem = ""
        $txtNotes.Text = ""

        $lblStatusBadge.Text = "PENDENTE"
        $lblStatusBadge.BackColor = [System.Drawing.Color]::FromArgb(254, 243, 199)
        $lblStatusBadge.ForeColor = [System.Drawing.Color]::FromArgb(146, 64, 14)
    }
    $script:SuppressAutoClass = $false

    $txtInst.Focus()
    $txtInst.SelectAll()

    if ($AutoOpenBrowser -and $chkAutoOpen.Checked) {
        Open-InFirefox -Query "`"$($c.Person_canonical)`""
    }
}

function Save-CurrentCandidate {
    $c = Get-CurrentCandidate
    if ($null -eq $c) { return $false }

    $inst = $txtInst.Text.Trim()
    $cls = [string]$cmbClass.SelectedItem
    $period = [string]$cmbPeriod.SelectedItem
    $url = $txtUrl.Text.Trim()
    $srcType = [string]$cmbSourceType.SelectedItem

    if ($cls -eq "CONFIRMADO_PUC" -and [string]::IsNullOrWhiteSpace($inst)) {
        $inst = "PUC-Rio"
    }

    # Exigir URL da fonte quando houver instituição/classificação positiva (se checkbox marcado)
    if ($chkRequireUrl.Checked -and $cls -ne "SEM_EVIDENCIA" -and [string]::IsNullOrWhiteSpace($url)) {
        $lblValidation.Text = "Faltou a URL da fonte! Cole com Ctrl+V / F4 (ou desmarque 'Exigir fonte')."
        $txtUrl.Focus()
        return $false
    }

    if ([string]::IsNullOrWhiteSpace($srcType) -and -not [string]::IsNullOrWhiteSpace($url)) {
        $srcType = Detect-SourceType -Url $url
    }

    $record = [PSCustomObject]@{
        OBM_Person_id         = $c.OBM_Person_id
        Person_canonical      = $c.Person_canonical
        OBM_Years             = $c.OBM_Years
        OBM_Cities            = $c.OBM_Cities
        Institution           = $inst
        Classification        = $cls
        Temporal_Relation_OBM = $period
        Relevant_Years        = $txtYears.Text.Trim()
        Source_Type           = $srcType
        Source_URL            = $url
        Evidence_Excerpt      = $txtNotes.Text.Trim()
        Updated_At            = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ss")
    }

    $script:SavedById[$c.OBM_Person_id] = $record
    Save-AllToCsv
    $lblValidation.Text = ""
    return $true
}

# ========================
# Eventos
# ========================
$btnSearchMain.Add_Click({
    $c = Get-CurrentCandidate
    if ($c) { Open-InFirefox -Query "`"$($c.Person_canonical)`"" }
})

$btnSearchPuc.Add_Click({
    $c = Get-CurrentCandidate
    if ($c) { Open-InFirefox -Query "`"$($c.Person_canonical)`" `"PUC-Rio`"" }
})

$btnSearchAcad.Add_Click({
    $c = Get-CurrentCandidate
    if ($c) { Open-InFirefox -Query "`"$($c.Person_canonical)`" Lattes OR Escavador" }
})

$btnPickFirefox.Add_Click({
    $dlg = New-Object System.Windows.Forms.OpenFileDialog
    $dlg.Title = "Selecione o executável do Firefox (firefox.exe)"
    $dlg.Filter = "Firefox (firefox.exe)|firefox.exe|Executáveis (*.exe)|*.exe"
    if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $script:FirefoxPath = $dlg.FileName
        Update-BrowserLabel
    }
})

$chkOnlyPending.Add_CheckedChanged({
    $c = Get-CurrentCandidate
    $keepId = if ($c) { $c.OBM_Person_id } else { $null }
    Rebuild-VisibleList -KeepPersonId $keepId
    Load-CurrentCandidateUI -AutoOpenBrowser $false
})

$cmbJump.Add_SelectedIndexChanged({
    if ($script:IsLoadingForm) { return }
    if ($cmbJump.SelectedIndex -ge 0) {
        $script:CurrentPos = $cmbJump.SelectedIndex
        Load-CurrentCandidateUI -AutoOpenBrowser $true
    }
})

$btnPrev.Add_Click({
    if ($script:VisibleIndices.Count -eq 0) { return }
    if ($script:CurrentPos -gt 0) {
        $script:CurrentPos--
        Load-CurrentCandidateUI -AutoOpenBrowser $true
    }
})

$btnNext.Add_Click({
    if ($script:VisibleIndices.Count -eq 0) { return }
    if ($script:CurrentPos -lt ($script:VisibleIndices.Count - 1)) {
        $script:CurrentPos++
        Load-CurrentCandidateUI -AutoOpenBrowser $true
    }
})

$btnSkip.Add_Click({
    if ($script:VisibleIndices.Count -eq 0) { return }
    if ($script:CurrentPos -lt ($script:VisibleIndices.Count - 1)) {
        $script:CurrentPos++
    } else {
        $script:CurrentPos = 0
    }
    Load-CurrentCandidateUI -AutoOpenBrowser $true
})

$btnSaveOnly.Add_Click({
    $c = Get-CurrentCandidate
    if (Save-CurrentCandidate) {
        Rebuild-VisibleList -KeepPersonId $c.OBM_Person_id
        Load-CurrentCandidateUI -AutoOpenBrowser $false
    }
})

$btnSaveNext.Add_Click({
    $c = Get-CurrentCandidate
    if (Save-CurrentCandidate) {
        if ($chkOnlyPending.Checked) {
            Rebuild-VisibleList
        } else {
            $oldPos = $script:CurrentPos
            Rebuild-VisibleList
            if ($oldPos + 1 -lt $script:VisibleIndices.Count) {
                $script:CurrentPos = $oldPos + 1
            }
        }
        Load-CurrentCandidateUI -AutoOpenBrowser $true
    }
})

# Atalhos de teclado globais
$form.Add_KeyDown({
    param($sender, $e)
    if ($e.KeyCode -eq [System.Windows.Forms.Keys]::F2) {
        $e.SuppressKeyPress = $true
        $btnSearchMain.PerformClick()
    } elseif ($e.KeyCode -eq [System.Windows.Forms.Keys]::F3) {
        $e.SuppressKeyPress = $true
        $btnSearchPuc.PerformClick()
    } elseif ($e.KeyCode -eq [System.Windows.Forms.Keys]::F4) {
        $e.SuppressKeyPress = $true
        Paste-UrlFromClipboard
    } elseif ($e.KeyCode -eq [System.Windows.Forms.Keys]::Escape) {
        $e.SuppressKeyPress = $true
        $btnSkip.PerformClick()
    } elseif ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter -and $btnSaveNext.Enabled) {
        if (-not ($cmbJump.DroppedDown -or $cmbClass.DroppedDown -or $cmbPeriod.DroppedDown -or $cmbSourceType.DroppedDown)) {
            $e.SuppressKeyPress = $true
            # Se estiver no campo Faculdade, exigir fonte estiver ativo e URL estiver vazia, pula direto para URL
            if ($txtInst.Focused -and $chkRequireUrl.Checked -and ([string]$cmbClass.SelectedItem -ne "SEM_EVIDENCIA") -and [string]::IsNullOrWhiteSpace($txtUrl.Text)) {
                $lblValidation.Text = "Agora cole a URL da fonte (Ctrl+V ou F4) e aperte Enter."
                $txtUrl.Focus()
            } else {
                $btnSaveNext.PerformClick()
            }
        }
    }
})

# Inicialização
Rebuild-VisibleList
$form.Add_Shown({
    Load-CurrentCandidateUI -AutoOpenBrowser $true
})

[void]$form.ShowDialog()
