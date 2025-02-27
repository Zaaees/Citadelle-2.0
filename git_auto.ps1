# Récupérer les 5 derniers commits
$commits = git log -n 5 --pretty=format:"%h - %s (%cr)" | Out-String

# Chargement des assemblies nécessaires
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Définition de la police et des couleurs
$fontRegular = New-Object System.Drawing.Font("Segoe UI", 10)
$fontHeader = New-Object System.Drawing.Font("Segoe UI Semibold", 12)
$colorBackground = [System.Drawing.Color]::FromArgb(240, 240, 240)
$colorHeader = [System.Drawing.Color]::FromArgb(45, 45, 48)
$colorHeaderText = [System.Drawing.Color]::White
$colorAccent = [System.Drawing.Color]::FromArgb(0, 120, 215)

# Création du formulaire principal
$form = New-Object System.Windows.Forms.Form
$form.Text = "Git Commit Manager"
$form.Size = New-Object System.Drawing.Size(600, 500)
$form.StartPosition = "CenterScreen"
$form.BackColor = $colorBackground
$form.Font = $fontRegular
$form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::FixedDialog
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.Icon = [System.Drawing.SystemIcons]::Application

# Panneau d'en-tête
$headerPanel = New-Object System.Windows.Forms.Panel
$headerPanel.Location = New-Object System.Drawing.Point(0, 0)
$headerPanel.Size = New-Object System.Drawing.Size(600, 60)
$headerPanel.BackColor = $colorHeader
$form.Controls.Add($headerPanel)

# Titre de l'application
$titleLabel = New-Object System.Windows.Forms.Label
$titleLabel.Location = New-Object System.Drawing.Point(20, 15)
$titleLabel.Size = New-Object System.Drawing.Size(400, 30)
$titleLabel.Text = "Git Commit Manager"
$titleLabel.Font = $fontHeader
$titleLabel.ForeColor = $colorHeaderText
$headerPanel.Controls.Add($titleLabel)

# Section des commits récents
$commitsGroupBox = New-Object System.Windows.Forms.GroupBox
$commitsGroupBox.Location = New-Object System.Drawing.Point(20, 80)
$commitsGroupBox.Size = New-Object System.Drawing.Size(550, 180)
$commitsGroupBox.Text = "Les 5 derniers commits"
$commitsGroupBox.Font = $fontRegular
$form.Controls.Add($commitsGroupBox)

# Remplacer la TextBox par un Label pour les commits
$commitsLabel = New-Object System.Windows.Forms.Label
$commitsLabel.Location = New-Object System.Drawing.Point(15, 25)
$commitsLabel.Size = New-Object System.Drawing.Size(520, 140)
$commitsLabel.Text = $commits
$commitsLabel.Font = New-Object System.Drawing.Font("Consolas", 9.5)
$commitsLabel.BorderStyle = [System.Windows.Forms.BorderStyle]::None
$commitsLabel.BackColor = [System.Drawing.Color]::White
$commitsGroupBox.Controls.Add($commitsLabel)

# Créer un Panel avec bordure pour contenir le Label
$commitsPanel = New-Object System.Windows.Forms.Panel
$commitsPanel.Location = New-Object System.Drawing.Point(15, 25)
$commitsPanel.Size = New-Object System.Drawing.Size(520, 140)
$commitsPanel.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$commitsPanel.BackColor = [System.Drawing.Color]::White
$commitsGroupBox.Controls.Add($commitsPanel)
$commitsPanel.Controls.Add($commitsLabel)

# Section du message de commit
$messageGroupBox = New-Object System.Windows.Forms.GroupBox
$messageGroupBox.Location = New-Object System.Drawing.Point(20, 280)
$messageGroupBox.Size = New-Object System.Drawing.Size(550, 120)
$messageGroupBox.Text = "Nouveau commit"
$messageGroupBox.Font = $fontRegular
$form.Controls.Add($messageGroupBox)

# Label pour le message de commit
$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(15, 25)
$label.Size = New-Object System.Drawing.Size(520, 20)
$label.Text = "Message de commit :"
$messageGroupBox.Controls.Add($label)

# Champ pour entrer le message
$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Location = New-Object System.Drawing.Point(15, 50)
$textBox.Size = New-Object System.Drawing.Size(520, 50)
$textBox.Multiline = $true
$textBox.BorderStyle = [System.Windows.Forms.BorderStyle]::FixedSingle
$messageGroupBox.Controls.Add($textBox)

# Bouton Commit & Push
$okButton = New-Object System.Windows.Forms.Button
$okButton.Location = New-Object System.Drawing.Point(330, 420)
$okButton.Size = New-Object System.Drawing.Size(150, 40)
$okButton.Text = "Commit && Push"
$okButton.BackColor = $colorAccent
$okButton.ForeColor = [System.Drawing.Color]::White
$okButton.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$okButton.Cursor = [System.Windows.Forms.Cursors]::Hand
$form.Controls.Add($okButton)

# Bouton Annuler
$cancelButton = New-Object System.Windows.Forms.Button
$cancelButton.Location = New-Object System.Drawing.Point(170, 420)
$cancelButton.Size = New-Object System.Drawing.Size(150, 40)
$cancelButton.Text = "Annuler"
$cancelButton.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$cancelButton.Cursor = [System.Windows.Forms.Cursors]::Hand
$cancelButton.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.Controls.Add($cancelButton)

# Configuration du formulaire
$form.AcceptButton = $okButton
$form.CancelButton = $cancelButton
$form.TopMost = $true

# Placer le focus dans la zone de texte du message de commit
$form.Shown += {
    $textBox.Focus()
}

# Affichage du formulaire
$result = $form.ShowDialog()

# Traitement du résultat
if ($result -eq [System.Windows.Forms.DialogResult]::OK)
{
    $commit_message = $textBox.Text.Trim()
    
    if ($commit_message -ne "") {
        try {
            # Ajouter tous les fichiers
            git add .
            
            # Faire le commit avec le message fourni
            git commit -m "$commit_message"
            
            # Pousser les modifications
            git push origin main --force
            
            [System.Windows.Forms.MessageBox]::Show("Commit et push effectués avec succès.", "Opération réussie", 
                [System.Windows.Forms.MessageBoxButtons]::OK, 
                [System.Windows.Forms.MessageBoxIcon]::Information)
        }
        catch {
            [System.Windows.Forms.MessageBox]::Show("Erreur lors de l'exécution des commandes Git: `n`n$_", 
                "Erreur", 
                [System.Windows.Forms.MessageBoxButtons]::OK, 
                [System.Windows.Forms.MessageBoxIcon]::Error)
        }
    } 
    else {
        [System.Windows.Forms.MessageBox]::Show("Le message de commit ne peut pas être vide.", 
            "Erreur", 
            [System.Windows.Forms.MessageBoxButtons]::OK, 
            [System.Windows.Forms.MessageBoxIcon]::Warning)
    }
}