# MarsAI + OpenHands Integration Plan

## Vision
CodeAct agent, kullanici ile chat UI'da konusur, bilgi toplar, MarsAI pipeline'ini
MCP tool olarak cagirarak profesyonel is akisi baslatir. Pipeline sonucunu alir,
sandbox'ta calistirir, kullaniciya gosterir. Kucuk degisiklikler icin pipeline'a
gerek kalmaz, CodeAct dogrudan duzenler.

---

## Architecture

```
Kullanici (Chat UI)
    |
    v
CodeAct Agent (OpenHands)
    |-- Microagent talimatlari (marsai_workflow.md)
    |-- MCP Tool: marsai-pipeline (stdio server)
    |-- Sandbox: kod calistir, preview goster
    |
    v (MCP call)
MarsAI MCP Server (Python stdio process)
    |
    v (HTTP API)
MarsAI Backend (CEO -> Departments -> Result)
```

---

## Implementation Steps

### PHASE 1: MarsAI MCP Server
**Amac:** MarsAI pipeline'ini CodeAct'in cagirabilecegi bir MCP tool olarak sunmak.

**Dosya:** `/home/ubuntu/OpenHands/.openhands/mcp_servers/marsai_server.py`

**Toollar:**
1. `marsai_run_pipeline` — Pipeline calistir (task, context, priority)
   - Input: {"task": str, "context": str, "priority": "low|medium|high"}
   - MarsAI API'yi cagirir (create_thread + stream_run)
   - Sonucu bekler, deliverable dondurur
   - Output: {"status": "completed|failed", "deliverable": str, "department": str, "quality_score": float}

2. `marsai_get_status` — Pipeline durumunu sorgula
   - Input: {"thread_id": str}
   - Output: {"status": str, "current_node": str, "department": str}

3. `marsai_list_departments` — Departman bilgilerini listele
   - Input: {}
   - Output: {"departments": [{"code": "cto", "name": "Engineering", "capabilities": [...]}]}

**Teknik:**
- fastmcp Python SDK ile stdio MCP server
- MarsAI API base URL: env var (MARSAI_API_URL)
- Senkron wait: pipeline bitene kadar bekle, sonucu don
- Timeout: 5 dakika (ayarlanabilir)

---

### PHASE 2: MarsAI Workflow Microagent
**Amac:** CodeAct'e MarsAI is akisini ogretmek — ne zaman kullaniciya soru sorsun,
ne zaman pipeline cagirsin, sonucu nasil islsin.

**Dosya:** `/home/ubuntu/OpenHands/.openhands/microagents/marsai_workflow.md`

**Tip:** `repo` (her zaman aktif)

**Icerik ozeti:**
```
Sen MarsAI Developer Platform'un asistanisin.

WORKFLOW:
1. Kullanici bir istek yaptiginda, once detaylari anla:
   - Ne tur bir proje? (web sitesi, mobil app, dashboard, API...)
   - Ozel gereksinimler? (tema, ozellikler, teknoloji tercihi...)
   - Hedef kitle?

2. Yeterli bilgi topladiktan sonra marsai_run_pipeline tool'unu cagir:
   - task: Kullanicinin istegi + toplanan detaylar (profesyonel brief)
   - context: Teknik gereksinimler
   - priority: Aciliyet seviyesi

3. Pipeline sonucu geldiginde:
   - Deliverable'daki kodu sandbox'ta calistir
   - Kod bloklari varsa dosyalari yaz ve server baslat
   - Sonucu kullaniciya ozetle

4. Kullanici kucuk degisiklik isterse (renk degistir, metin guncelle):
   - Pipeline'a gerek yok, dogrudan sandbox'ta duzenle

5. Buyuk degisiklik isterse (yeni sayfa ekle, mimari degisiklik):
   - Pipeline'i tekrar cagir
```

---

### PHASE 3: OpenHands Konfigurasyonu
**Amac:** Fork'u MarsAI branding + config ile yapilandirmak.

**Dosyalar:**

1. **`.openhands/microagents/marsai_workflow.md`** — Phase 2 microagent
2. **`.openhands/microagents/marsai_capabilities.md`** — Knowledge microagent
   - Triggers: ["marsai", "pipeline", "department", "ceo", "cto"]
   - MarsAI'nin departman yapisi, yetenekleri
3. **`config.toml`** — Default LLM ayarlari (Gemini)
4. **`containers/app/Dockerfile`** — Ek bagimliliklar (fastmcp)
5. **`docker-compose.marsai.yml`** — Production compose (MarsAI backend ile birlikte)

---

### PHASE 4: Sandbox Deploy Logic
**Amac:** Pipeline sonucundaki kodu sandbox'ta calistirmak.

**Yaklasim:** CodeAct bunu zaten yapiyor! Microagent talimatlarinda:
- "Kod bloklari varsa dosyalari /workspace/project/ altina yaz"
- "HTML projesi ise python -m http.server 8011 baslat"
- "React/Next.js ise npm install && npm run dev -- --port 8011"
- CodeAct bash/ipython tool'lariyla bunlari dogrudan yapar

Bu, adapter_openhands/pipeline_bridge.py'deki _deploy_code_to_sandbox
mantigi ile ayni — ama CodeAct native olarak yapiyor, ekstra kod gerekmez.

---

### PHASE 5: MarsAI Branding
**Amac:** OpenHands UI'yi MarsAI markasi ile ozelestirmek.

**Degisiklikler:**
1. Logo ve favicon (eski fork'tan kopyala)
2. Baslik: "MarsAI Developer Platform"
3. Renk paleti: #E8553A (Mars red)
4. i18n: OpenHands -> MarsAI

**Kaynak:** /home/ubuntu/OpenHands-old/ (eski branding fork)

---

### PHASE 6: Docker Production Deploy
**Amac:** Butun sistemi docker-compose ile ayaga kaldirmak.

**docker-compose.marsai.yml:**
```yaml
services:
  openhands:
    build: .
    ports:
      - "3000:3000"
    environment:
      - WORKSPACE_BASE=/opt/workspace
      - SANDBOX_RUNTIME_CONTAINER_IMAGE=ghcr.io/openhands/agent-server:latest
      - LLM_MODEL=gemini/gemini-2.0-flash
      - LLM_API_KEY=${GOOGLE_API_KEY}
      - MARSAI_API_URL=http://marsai:8000
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - openhands_data:/.openhands

  marsai:
    # Mevcut MarsAI backend (ayni docker-compose.prod.yml'dan)
    build: /home/ubuntu/marsai-automation-agent
    ports:
      - "8000:8000"
    depends_on:
      - marsai-postgres
      - marsai-redis
```

---

## File Map

| # | Dosya | Islem | Aciklama |
|---|-------|-------|----------|
| 1 | `.openhands/mcp_servers/marsai_server.py` | OLUSTUR | MarsAI MCP server (fastmcp stdio) |
| 2 | `.openhands/microagents/marsai_workflow.md` | OLUSTUR | Repo microagent — is akisi talimatlari |
| 3 | `.openhands/microagents/marsai_capabilities.md` | OLUSTUR | Knowledge microagent — departman bilgisi |
| 4 | `config.toml` | OLUSTUR | Default ayarlar |
| 5 | `containers/app/Dockerfile` | DUZENLE | fastmcp bagimliligi ekle |
| 6 | `docker-compose.marsai.yml` | OLUSTUR | Production compose |
| 7 | Frontend branding dosyalari | DUZENLE | Logo, renk, baslik |

---

## Execution Order

```
Phase 1 → MCP Server (MarsAI API wrapper)
Phase 2 → Microagent (CodeAct talimatlari)
Phase 3 → Config (LLM, environment)
Phase 4 → Sandbox logic (microagent'ta talimat olarak)
Phase 5 → Branding (UI ozellestirme)
Phase 6 → Docker deploy (production)
```

Phase 1-3 tamamlaninca test edilebilir (dev mode).
Phase 4-6 production icin.

---

## Test Senaryosu

1. OpenHands'i dev modda baslat
2. Yeni conversation ac
3. "Bana bir landing page yap" yaz
4. CodeAct soru sormali (tema, ozellik, sayfa sayisi...)
5. Cevap ver
6. CodeAct marsai_run_pipeline tool'unu cagirmali
7. Pipeline calismali (CEO -> CTO -> Web team)
8. Sonuc gelmeli, CodeAct kodu sandbox'a yazmali
9. Port 8011'de preview gorunmeli
10. "Header rengini kirmizi yap" de → CodeAct dogrudan duzenlemeli
