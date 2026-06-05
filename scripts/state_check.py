import os, re, subprocess

base = os.path.expanduser('~/Desktop/joaobonin.com/inputs_posts/')
posts_dir = os.path.expanduser('~/Desktop/joaobonin.com/content/posts/')

exclude_file = base + '.exclude'
exclude = set(open(exclude_file).read().splitlines() if os.path.exists(exclude_file) else [])

pending_file = base + '.pending-commit'
pending_commit = open(pending_file).read().strip().splitlines() if os.path.exists(pending_file) else []

folders = sorted([d for d in os.listdir(base)
                  if os.path.isdir(base+d) and d not in exclude and not d.startswith('.')])

total = 0; has_post_count = 0; has_linkedin_count = 0
for f in folders:
    path = base + f + '/'
    contents = os.listdir(path)
    has_default = 'default_template.rtfd' in contents
    dated = [x for x in contents if re.match(r'\d{4}-\d{2}-\d{2}\.rtfd', x)]
    has_post = os.path.exists(posts_dir + f + '.md')
    has_linkedin = 'linkedin-draft.md' in contents

    rooted = True
    if has_default and not has_post:
        rtfd_path = path + 'default_template.rtfd/'
        rtf = rtfd_path + 'TXT.rtf'
        text_rooted = False
        screenshot_rooted = False

        if os.path.exists(rtf):
            try:
                txt = subprocess.check_output(['textutil', '-convert', 'txt', '-stdout', rtf], text=True)
                text_rooted = ('root.txt' in txt.lower() or 'proof.txt' in txt.lower() or bool(re.search(r'[0-9a-f]{32}', txt.lower())))
            except Exception as e:
                print('RTF_ERR ' + f + ': ' + str(e))

        if not text_rooted and os.path.exists(rtfd_path):
            try:
                pngs = sorted([fn for fn in os.listdir(rtfd_path) if fn.lower().endswith('.png')])
                if pngs:
                    last_png = rtfd_path + pngs[-1]
                    ocr_lines = [
                        'import Vision, Foundation',
                        'url = Foundation.NSURL.fileURLWithPath_("' + last_png + '")',
                        'handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(url, {})',
                        'req = Vision.VNRecognizeTextRequest.alloc().init()',
                        'req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)',
                        'handler.performRequests_error_([req], None)',
                        'for obs in (req.results() or []):',
                        '    for c in obs.topCandidates_(1):',
                        '        print(c.string())',
                    ]
                    ocr_out = subprocess.check_output(['python3', '-c', '\n'.join(ocr_lines)], text=True, stderr=subprocess.DEVNULL)
                    screenshot_rooted = bool(re.search(r'[0-9a-f]{32}', ocr_out.lower()))
            except Exception as e:
                print('OCR_ERR ' + f + ': ' + str(e))

        rooted = text_rooted or screenshot_rooted

    total += 1
    if has_post: has_post_count += 1
    if has_linkedin: has_linkedin_count += 1
    print(f + '|default=' + str(has_default) + '|dated=' + str(dated) + '|post=' + str(has_post) + '|linkedin=' + str(has_linkedin) + '|rooted=' + str(rooted))

print('PENDING=' + ','.join(pending_commit))
print('PROGRESS=' + str(has_post_count) + '/' + str(total) + ' posts done, ' + str(has_linkedin_count) + ' with LinkedIn draft')
