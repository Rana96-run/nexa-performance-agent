with open('script_original.js', 'rb') as f:
    content = f.read()

old = b"      setFieldValue('browser', browser);\r\n    }\r\n"
new = (
    b"      setFieldValue('browser', browser);\r\n"
    b"\r\n"
    b"      // ---- UTM params (read from URL, persist in cookie for cross-page attribution)\r\n"
    b"      ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term', 'utm_audience'].forEach(function (p) {\r\n"
    b"        var val = getParam(p) || getCookie('lp_' + p);\r\n"
    b"        if (getParam(p)) setCookie('lp_' + p, getParam(p), 30);\r\n"
    b"        setFieldValue(p, val);\r\n"
    b"      });\r\n"
    b"\r\n"
    b"      // ---- Google Ads IDs (passed as ValueTrack params in final URL)\r\n"
    b"      setFieldValue('campaign_id',   getParam('campaign_id'));\r\n"
    b"      setFieldValue('ad_group_id',   getParam('ad_group_id'));\r\n"
    b"      setFieldValue('field_beb550d', getParam('ad_id'));\r\n"
    b"    }\r\n"
)

if old not in content:
    print('ERROR: old block not found')
    idx = content.find(b"setFieldValue('browser'")
    print(repr(content[idx:idx+40]))
else:
    updated = content.replace(old, new, 1)
    with open('script_updated.js', 'wb') as f:
        f.write(updated)
    print('Patched OK, saved', len(updated), 'bytes')
    if b'utm_source' in updated:
        print('UTM block confirmed present')
