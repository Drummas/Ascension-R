# Ascension-R's own Xbox button icons, for the game's button textures (an optional texture mod, port/textures.h):
# a dark disc with a coloured letter for each face button, as the game's PlayStation ones are a dark disc with a
# coloured symbol, and the View button on a dark pill for the Select bar. Drawn here with Windows' GDI+, no picture
# of anyone else's. The PNGs it writes are in the tree, in the mod (optional-mods/Xbox button icons/textures/), each
# named by the id of the game's texture it stands for.
#
#   powershell -ExecutionPolicy Bypass -File scripts\button_icons.ps1
param([string]$Out = (Join-Path $PSScriptRoot "..\optional-mods\Xbox button icons\textures"))
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force $Out | Out-Null

function New-Canvas([int]$w, [int]$h) {
    $bmp = New-Object System.Drawing.Bitmap $w, $h, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $g.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $g.Clear([System.Drawing.Color]::Transparent)
    return @($bmp, $g)
}

# The disc: dark, lighter at the top, a grey rim and a soft highlight, as the game's are.
function Draw-Disc($g, [float]$x, [float]$y, [float]$d) {
    $r = New-Object System.Drawing.RectangleF $x, $y, $d, $d
    $fill = New-Object System.Drawing.Drawing2D.LinearGradientBrush $r, ([System.Drawing.Color]::FromArgb(255, 74, 74, 78)), ([System.Drawing.Color]::FromArgb(255, 16, 16, 18)), 90.0
    $g.FillEllipse($fill, $r)
    $hi = New-Object System.Drawing.RectangleF ($x + $d * 0.18), ($y + $d * 0.06), ($d * 0.64), ($d * 0.34)
    $glow = New-Object System.Drawing.Drawing2D.LinearGradientBrush $hi, ([System.Drawing.Color]::FromArgb(70, 255, 255, 255)), ([System.Drawing.Color]::FromArgb(0, 255, 255, 255)), 90.0
    $g.FillEllipse($glow, $hi)
    $rim = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 118, 118, 124)), ($d * 0.03)
    $g.DrawEllipse($rim, ($x + $d * 0.015), ($y + $d * 0.015), ($d * 0.97), ($d * 0.97))
}

# A letter in the middle of (cx, cy), its outline's bounds centred, in colour with a dark edge.
function Draw-Letter($g, [string]$s, [float]$cx, [float]$cy, [float]$size, [System.Drawing.Color]$col) {
    $p = New-Object System.Drawing.Drawing2D.GraphicsPath
    $fam = New-Object System.Drawing.FontFamily "Segoe UI"
    $p.AddString($s, $fam, [int][System.Drawing.FontStyle]::Bold, $size, (New-Object System.Drawing.PointF 0, 0), [System.Drawing.StringFormat]::GenericTypographic)
    $b = $p.GetBounds()
    $m = New-Object System.Drawing.Drawing2D.Matrix
    $m.Translate(($cx - $b.X - $b.Width / 2), ($cy - $b.Y - $b.Height / 2))
    $p.Transform($m)
    $edge = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(200, 0, 0, 0)), ($size * 0.07)
    $edge.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
    $g.DrawPath($edge, $p)
    $g.FillPath((New-Object System.Drawing.SolidBrush $col), $p)
}

# The face buttons, by where each is on the pad: Cross is A, Circle B, Square X, Triangle Y.
$face = @(
    @{ Name = "d8c17e20cbbe71ac_A"; Letter = "A"; Color = [System.Drawing.Color]::FromArgb(255, 96, 186, 56) },
    @{ Name = "1f52688dc50e2bfb_B"; Letter = "B"; Color = [System.Drawing.Color]::FromArgb(255, 228, 52, 46) },
    @{ Name = "2133aab0625680af_X"; Letter = "X"; Color = [System.Drawing.Color]::FromArgb(255, 44, 128, 222) },
    @{ Name = "660940394f9aee54_Y"; Letter = "Y"; Color = [System.Drawing.Color]::FromArgb(255, 246, 192, 28) }
)
foreach ($f in $face) {
    $bmp, $g = New-Canvas 128 128
    Draw-Disc $g 2 2 124
    Draw-Letter $g $f.Letter 64 65 76 $f.Color
    $g.Dispose()
    $bmp.Save((Join-Path $Out "$($f.Name).png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

# The View button on the Select bar's pill: two windows, one over the other.
$bmp, $g = New-Canvas 128 64
$pill = New-Object System.Drawing.Drawing2D.GraphicsPath
$pill.AddArc(2, 2, 60, 60, 90, 180); $pill.AddArc(66, 2, 60, 60, 270, 180); $pill.CloseFigure()
$fill = New-Object System.Drawing.Drawing2D.LinearGradientBrush (New-Object System.Drawing.RectangleF 2, 2, 124, 60), ([System.Drawing.Color]::FromArgb(255, 74, 74, 78)), ([System.Drawing.Color]::FromArgb(255, 16, 16, 18)), 90.0
$g.FillPath($fill, $pill)
$g.DrawPath((New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 118, 118, 124)), 3), $pill)
$white = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 236, 236, 236)), 5
$white.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
$g.DrawRectangle($white, 44, 16, 30, 22)
$g.FillRectangle((New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 236, 236, 236))), 56, 27, 30, 22)
$g.Dispose()
$bmp.Save((Join-Path $Out "a4f295497b5454b7_View.png"), [System.Drawing.Imaging.ImageFormat]::Png)
$bmp.Dispose()
Get-ChildItem $Out -Filter "*.png" | ForEach-Object { "{0} {1} bytes" -f $_.Name, $_.Length }
