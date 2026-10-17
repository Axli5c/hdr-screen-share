function New-HssVddConfig([string]$SourcePath) {
    [xml]$configuration = Get-Content -LiteralPath $SourcePath
    $globalNode = $configuration.SelectSingleNode('/vdd_settings/global')
    $modesNode = $configuration.SelectSingleNode('/vdd_settings/resolutions')
    if ($null -eq $globalNode -or $null -eq $modesNode) { throw 'Invalid VDD configuration' }
    $globalNode.RemoveAll()
    $rate = $configuration.CreateElement('g_refresh_rate'); $rate.InnerText = '60'
    $globalNode.AppendChild($rate) | Out-Null
    foreach ($resolution in $modesNode.SelectNodes('resolution')) {
        $resolution.SelectSingleNode('refresh_rate').InnerText = '60'
    }
    $portrait = $configuration.CreateElement('resolution')
    foreach ($pair in @(@('width','2160'),@('height','3840'),@('refresh_rate','60'))) {
        $node = $configuration.CreateElement($pair[0]); $node.InnerText = $pair[1]
        $portrait.AppendChild($node) | Out-Null
    }
    $modesNode.AppendChild($portrait) | Out-Null
    return ,$configuration
}
