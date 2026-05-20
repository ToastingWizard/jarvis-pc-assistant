Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)

' Try pythonw first (no console window)
pythonw = "pythonw.exe"
script = dir & "\JARVIS_app.py"

On Error Resume Next
sh.Run """" & pythonw & """ """ & script & """", 0, False
If Err.Number <> 0 Then
    ' Fall back to python if pythonw not found
    Err.Clear
    sh.Run "python """ & script & """", 0, False
End If
