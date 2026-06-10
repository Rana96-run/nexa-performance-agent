import requests, re, base64

s = requests.Session()
s.cookies.set('wordpress_test_cookie', 'WP Cookie check')

# Log in
login_data = {
    'log': 'Content-OS',
    'pwd': 'ks1c wZ6h HKR8 kcFs xkQj JzjC',
    'wp-submit': 'Log In',
    'redirect_to': '/wp-admin/',
    'testcookie': '1',
}
r = s.post('https://lp.qoyod.com/wp-login.php', data=login_data, timeout=30, allow_redirects=True)
print('Login:', r.status_code, r.url)
logged_in = any('wordpress_logged_in' in c.name for c in s.cookies)
print('Logged in:', logged_in)

if not logged_in:
    print('Login failed — cannot upload')
    exit(1)

# Get the theme editor page for script.js to extract nonce
editor_url = 'https://lp.qoyod.com/wp-admin/theme-editor.php?file=script.js&theme=hello-theme-child-master'
editor_page = s.get(editor_url, timeout=30)
print('Editor page:', editor_page.status_code)

nonce_match = re.search(r'name="_wpnonce"\s+value="([^"]+)"', editor_page.text)
if not nonce_match:
    nonce_match = re.search(r'"nonce"\s*:\s*"([a-f0-9]+)"', editor_page.text)
print('Nonce found:', bool(nonce_match))
if nonce_match:
    nonce = nonce_match.group(1)
    print('Nonce:', nonce)

    with open('script_updated.js', 'r', encoding='utf-8') as f:
        new_content = f.read()

    # Submit the theme editor form
    post_data = {
        'action': 'edit-theme-plugin-file',
        'file': 'script.js',
        'theme': 'hello-theme-child-master',
        'newcontent': new_content,
        '_wpnonce': nonce,
    }
    save_r = s.post('https://lp.qoyod.com/wp-admin/theme-editor.php', data=post_data, timeout=30)
    print('Save status:', save_r.status_code)
    if 'updated' in save_r.text.lower() or 'success' in save_r.text.lower():
        print('SUCCESS: file saved')
    else:
        # Check for error message
        err = re.search(r'class="error[^"]*"[^>]*>(.*?)</div>', save_r.text, re.DOTALL)
        if err:
            print('Error:', err.group(1)[:200])
        else:
            print('Response snippet:', save_r.text[:300])
