// setting up form fields
(function () {

    function getParam(name) {
      const url = new URL(window.location.href);
      return url.searchParams.get(name) || '';
    }
  
    function setCookie(name, value, days) {
      if (!value) return;
      const d = new Date();
      d.setTime(d.getTime() + (days * 24 * 60 * 60 * 1000));
      document.cookie =
        name + '=' + encodeURIComponent(value) +
        '; expires=' + d.toUTCString() +
        '; path=/; SameSite=Lax';
    }
  
    function getCookie(name) {
      const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const match = document.cookie.match(new RegExp('(?:^|; )' + escaped + '=([^;]*)'));
      return match ? decodeURIComponent(match[1]) : '';
    }
  
    function setFieldValue(fieldName, value) {
      if (!value) return;
  
      const selector = 'input[name="form_fields[' + fieldName + ']"]';
  
      document.querySelectorAll(selector).forEach(function (el) {
        el.value = value;
        el.setAttribute('value', value);
  
        // Trigger Elementor update
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
    }
  
    function parseGclidFromGclAw(cookieValue) {
      if (!cookieValue) return '';
      const parts = cookieValue.split('.');
      return parts.length >= 3 ? parts.slice(2).join('.') : '';
    }
  
    function detectDeviceType() {
      if (navigator.userAgentData && typeof navigator.userAgentData.mobile === 'boolean') {
        return navigator.userAgentData.mobile ? 'mobile' : 'pc';
      }
  
      return /Android|iPhone|iPad|iPod/i.test(navigator.userAgent)
        ? 'mobile'
        : 'pc';
    }
  
    function detectOS() {
      const ua = navigator.userAgent;
  
      if (/Windows/i.test(ua)) return 'Windows';
      if (/Mac OS X/i.test(ua)) return 'macOS';
      if (/Android/i.test(ua)) return 'Android';
      if (/iPhone|iPad|iPod/i.test(ua)) return 'iOS';
      if (/Linux/i.test(ua)) return 'Linux';
  
      return 'Unknown';
    }
  
    function detectBrowser() {
      const ua = navigator.userAgent;
  
      if (/Edg\//i.test(ua)) return 'Edge';
      if (/OPR\//i.test(ua)) return 'Opera';
      if (/SamsungBrowser/i.test(ua)) return 'Samsung';
      if (/Chrome/i.test(ua) && !/Edg|OPR|SamsungBrowser/i.test(ua)) return 'Chrome';
      if (/Firefox/i.test(ua)) return 'Firefox';
      if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) return 'Safari';
  
      return 'Unknown';
    }
  
    function runTracking() {
  
      // ---- URL params
      let msclkid = getParam('msclkid');
      let ttclid  = getParam('ttclid');
      let sccid   = getParam('sccid');
      let gclid   = getParam('gclid');
  
      // ---- Save to cookies (first touch)
      if (msclkid) setCookie('msclkid', msclkid, 90);
      if (ttclid)  setCookie('ttclid', ttclid, 90);
      if (sccid)   setCookie('sccid', sccid, 90);
      if (gclid)   setCookie('gclid', gclid, 90);
  
      // ---- Fallback from cookies
      if (!msclkid) msclkid = getCookie('msclkid');
      if (!ttclid)  ttclid  = getCookie('ttclid');
      if (!sccid)   sccid   = getCookie('sccid');
  
      // ---- Facebook browser ID
      const fbp = getCookie('_fbp');
  
      // ---- GCLID fallback
      if (!gclid) gclid = getCookie('gclid');
  
      if (!gclid) {
        const gclAw = getCookie('_gcl_aw');
        gclid = parseGclidFromGclAw(gclAw);
      }
  
      // ---- Client data
      const deviceType = detectDeviceType();
      const os = detectOS();
      const browser = detectBrowser();
  
      // ---- Fill Elementor fields
      setFieldValue('msclkid', msclkid);
      setFieldValue('ttclid', ttclid);
      setFieldValue('sccid', sccid);
      setFieldValue('fbp', fbp);
      setFieldValue('gclid', gclid);
      setFieldValue('device_type', deviceType);
      setFieldValue('os', os);
      setFieldValue('browser', browser);
    }
  
    // ---- Run on load
    document.addEventListener('DOMContentLoaded', runTracking);
  
    // ---- IMPORTANT: Elementor loads forms via JS sometimes
    // So run again after a short delay
    window.addEventListener('load', function () {
      setTimeout(runTracking, 500);
      setTimeout(runTracking, 1500);
    });
  
  })();

  // getting page url to form field
  function setPageURL() {
    const url = window.location.href;
  
    document.querySelectorAll('input[name="form_fields[page_url]"]').forEach(function (el) {
      el.value = url;
      el.setAttribute('value', url);
    });
  }
  
  document.addEventListener('DOMContentLoaded', setPageURL);
  window.addEventListener('load', function () {
    setTimeout(setPageURL, 500);
  });