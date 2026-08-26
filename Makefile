.PHONY: cloc

cloc:
	cloc --vcs=git --fullpath --not-match-d='(^|/)data(/|$$)' --not-match-f='(^|/)index\.html$$' .
