# VHS tape for the README demo GIF.
#
# Regenerate with:
#   python3 docs/demo/make_demo_bugreport.py   # (re)create the sample bugreport
#   cd docs/demo && vhs demo.tape              # render demo.gif
#
# Requires: brew install vhs

Output demo.gif

Set FontSize 14
Set Width 960
Set Height 700
Set Padding 16
Set Theme "Catppuccin Mocha"
Set TypingSpeed 45ms

# Invisible setup: make `ailog` resolve to the repo checkout, clean screen.
Hide
Type "alias ailog='python3 ../../run.py' && clear"
Enter
Show

Sleep 800ms
Type "ailog bugreport bugreport-car-demo.zip --no-ai"
Sleep 600ms
Enter
Sleep 9s
