rem get files.txt first by calling mpremote ls
for /f "tokens=*" %%f in (files.txt) do (
	call mpremote cp :%%f src/
)