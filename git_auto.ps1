# Afficher les 5 derniers commits
Write-Host "Les 5 derniers commits :"
Write-Host "------------------------"
git log -n 5 --pretty=format:"%h - %s (%cr)"
Write-Host "`n------------------------`n"

# Créer une boîte de dialogue pour entrer le message
Add-Type -AssemblyName System.Windows.Forms
$form = New-Object System.Windows.Forms.Form
$form.Text = "Git Commit"
$form.Size = New-Object System.Drawing.Size(400,200)
$form.StartPosition = "CenterScreen"

$label = New-Object System.Windows.Forms.Label
$label.Location = New-Object System.Drawing.Point(10,20)
$label.Size = New-Object System.Drawing.Size(380,20)
$label.Text = "Entrez le message de commit:"
$form.Controls.Add($label)

$textBox = New-Object System.Windows.Forms.TextBox
$textBox.Location = New-Object System.Drawing.Point(10,50)
$textBox.Size = New-Object System.Drawing.Size(360,20)
$form.Controls.Add($textBox)

$okButton = New-Object System.Windows.Forms.Button
$okButton.Location = New-Object System.Drawing.Point(100,120)
$okButton.Size = New-Object System.Drawing.Size(75,23)
$okButton.Text = "OK"
$okButton.DialogResult = [System.Windows.Forms.DialogResult]::OK
$form.Controls.Add($okButton)

$form.AcceptButton = $okButton
$form.TopMost = $true

$result = $form.ShowDialog()

if ($result -eq [System.Windows.Forms.DialogResult]::OK)
{
    $commit_message = $textBox.Text
    
    # Ajouter tous les fichiers
    git add .
    
    # Faire le commit avec le message fourni
    git commit -m "$commit_message"
    
    # Pousser les modifications
    git push origin main --force
    
    Write-Host "Commit et push effectués avec succès."
}
else 
{
    Write-Host "Opération annulée."
}

Write-Host "`nAppuyez sur Entrée pour fermer..."
Read-Host