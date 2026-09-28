# 🚀 Hostinger Shared Hosting & Free Backend Deployment Guide

Yeh Guide bataati hai ki is **SEO Auditor SaaS Web Application** ko **Hostinger Shared Hosting** par bina kisi extra VPS budget ke kaise deploy karna hai.

---

## 📁 1. Hostinger Shared Hosting Par Frontend Upload Karna

1. **Hostinger hPanel** me Login karein ➔ **File Manager** kholein.
2. `public_html` folder me jayein.
3. Is project ke `public_html` folder ki teeno files upload kar dein:
   - `index.html`
   - `style.css`
   - `app.js`

Aapki website (e.g. `https://yourdomain.com`) turant live dikhne lagegi!

---

## 🐍 2. Free Python Backend Deploy Karna ($0 VPS Budget)

Crawling heavy task hai, isliye backend API ko **Render.com** (Free Tier) par 1-click me deploy kar sakte hain:

1. [Render.com](https://render.com) par free account banayein.
2. **New +** ➔ **Web Service** par click karein.
3. Is GitHub project repository ko connect karein.
4. Render automatic detect kar lega:
   - **Environment**: Python 3
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. **Create Web Service** par click karein. Render aapko ek free API URL de dega (e.g. `https://seo-auditor-api.onrender.com`).

---

## 🔗 3. Hostinger Frontend ko Backend se Connect Karna

Upload hone ke baad, `public_html/index.html` file khol kar top me script add kar dein (ya `app.js` me `window.SEO_API_URL` set kar dein):

```html
<script>
    window.SEO_API_URL = "https://seo-auditor-api.onrender.com";
</script>
```

Bas! Aapka SaaS SEO Auditor Tool Hostinger Shared Hosting par live aur ready hai! 🎉

---

## 💻 Local Machine Par Run & Test Karna

Local test karne ke liye:
```bash
# 1. FastAPI server start karein
uvicorn server:app --reload

# 2. Browser me public_html/index.html open karein ya live server chalayein
```
