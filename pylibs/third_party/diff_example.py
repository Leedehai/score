# https://www.agiliq.com/blog/2014/05/google-diff-match-patch-library/

from pathlib import Path

import diff_match_patch

old_string = """I'm selfish, impatient and a little insecure. I make mistakes,
I am out of control and at times hard to handle. But if you can't handle me at my worst, But if you can't handle me at my worst, But if you can't handle me at my worst, But if you can't handle me at my worst,
He had stayed so close that the old man was afraid he would cut the line with his tail which was sharp as a scythe and almost of that size and shape. When the old man had gaffed her and clubbed her, holding the rapier bill with its sandpaper edge and clubbing her across the top of her head until her colour turned to a colour almost like the backing of mirrors, and then, with the boy’s aid, hoisted her aboard, the male fish had stayed by the side of the boat.
then you sure as hell don't deserve me at my best."""

new_string = """I'm selfish, impatient and a little secure. I don't make mistakes,
I am out of control and at times hard to handle difficult things. But if you can't handle me at my worst,
then you sure as hell don't deserve me at my best."""


class SideBySideDiff(diff_match_patch.diff_match_patch):
    def old_content(self, diffs) -> str:
        """
        Returns HTML representation of 'deletions'
        """
        html = []
        for (flag, data) in diffs:
            text = (data.replace("&", "&amp;").replace("<", "&lt;").replace(
                ">", "&gt;").replace("\n", "<span class='br'>↵</span><br>"))
            if flag == self.DIFF_DELETE:
                html.append("""<span style=\"background:salmon;
                    \">%s</span>""" % text)
            elif flag == self.DIFF_EQUAL:
                html.append("<span>%s</span>" % text)
        return "".join(html)

    def new_content(self, diffs) -> str:
        """
        Returns HTML representation of 'insertions'
        """
        html = []
        for (flag, data) in diffs:
            text = (data.replace("&", "&amp;").replace("<", "&lt;").replace(
                ">", "&gt;").replace("\n", "<span class='br'>↵</span><br>"))
            if flag == self.DIFF_INSERT:
                html.append("""<span style=\"background:mediumspringgreen;
                    \">%s</span>""" % text)
            elif flag == self.DIFF_EQUAL:
                html.append("<span>%s</span>" % text)
        return "".join(html)


diff_obj = SideBySideDiff()
result = diff_obj.diff_main(old_string, new_string)
diff_obj.diff_cleanupSemantic(result)
old_record = diff_obj.old_content(result)
new_record = diff_obj.new_content(result)

html_str = f"""
<html>
<head>
    <style>
        span.br {{
            user-select: none;
            color: silver;
        }}
    </style>
</head>
<body>
<div style="width: 50em; float: left; margin: 2%;">
    <h1>Old record</h1>
    <span style="font-family: monospace;">{old_record}</span>
</div>
<div style="width: 50em; float: left; margin: 2%;">
    <h1>New record</h1>
    <span style="font-family: monospace;">{new_record}</span>
</div>
</body>
</html>
"""

with open(Path(__file__).parent.joinpath("diff_1.html"), 'w') as f:
    f.write(html_str)
