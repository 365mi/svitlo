with open("test_final.html", "r", encoding="utf-8") as f:
    html = f.read()

# Verify base structure
assert '<meta name="monetag" content="b7981e6d39fbf8418ecd653ef26b9815" />' in html

# 1. Add Monetag Telegram Mini App SDK tag in <head> (only defines show_12348913, does not show ads until called)
tma_sdk_tag = "  <script src='https://libtl.com/sdk.js' data-zone='12348913' data-sdk='show_12348913'></script>\n"
html = html.replace(
    '  <script src="https://telegram.org/js/telegram-web-app.js"></script>\n',
    '  <script src="https://telegram.org/js/telegram-web-app.js"></script>\n' + tma_sdk_tag,
    1
)

# 2. Add CSS for Support / VIP action bar & modals
extra_css = '''
    /* Support & VIP Action Row */
    .support-bar {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
    }

    .sup-btn {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
      padding: 7px 8px;
      border-radius: 10px;
      font-size: 11px;
      font-weight: 800;
      cursor: pointer;
      border: 1px solid transparent;
      white-space: nowrap;
      text-align: center;
    }

    .sup-btn.vip {
      background: rgba(245, 158, 11, 0.12);
      border-color: rgba(245, 158, 11, 0.42);
      color: #fbbf24;
    }

    .sup-btn.vip.active-vip {
      background: rgba(34, 197, 94, 0.12);
      border-color: rgba(34, 197, 94, 0.4);
      color: #4ade80;
    }

    .sup-btn.donate {
      background: rgba(56, 189, 248, 0.11);
      border-color: rgba(56, 189, 248, 0.38);
      color: #38bdf8;
    }

    .pay-card-box {
      background: #090b0f;
      border: 1px solid #2a3242;
      border-radius: 12px;
      padding: 10px 12px;
      display: flex;
      flex-direction: column;
      gap: 7px;
      text-align: center;
    }

    .pay-card-num {
      font-size: 17px;
      font-weight: 800;
      letter-spacing: 1px;
      color: #ffffff;
      font-variant-numeric: tabular-nums;
    }

    .pay-copy-btn {
      background: #1e293b;
      border: 1px solid #334155;
      color: #f8fafc;
      border-radius: 8px;
      padding: 7px 10px;
      font-size: 12px;
      font-weight: 700;
      cursor: pointer;
    }

    .pay-copy-btn.copied {
      background: rgba(34, 197, 94, 0.2);
      border-color: #22c55e;
      color: #4ade80;
    }

    .donate-amounts {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 5px;
    }

    .amt-chip {
      background: #131722;
      border: 1px solid #283042;
      border-radius: 8px;
      padding: 7px 4px;
      color: #e2e8f0;
      font-size: 11.5px;
      font-weight: 800;
      cursor: pointer;
      text-align: center;
    }

    .amt-chip.active {
      background: rgba(56, 189, 248, 0.2);
      border-color: var(--blue);
      color: #ffffff;
    }

    .pay-cta-link {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      background: #22c55e;
      color: #052e16;
      text-decoration: none;
      font-size: 12.5px;
      font-weight: 800;
      padding: 9px 12px;
      border-radius: 10px;
      text-align: center;
    }

    .pay-cta-link.blue {
      background: #38bdf8;
      color: #082f49;
    }

    .pay-note {
      font-size: 11px;
      color: var(--muted);
      line-height: 1.4;
    }
'''

html = html.replace('  </style>', extra_css + '  </style>', 1)

# 3. Ensure queueMenu has no max-height scroll and readable font (14px)
html = html.replace(
'''    .queue-menu {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      width: 100%;
      min-width: 96px;
      background: #11151e;
      border: 1px solid #2b3240;
      border-radius: 10px;
      padding: 3px;
      display: none;
      flex-direction: column;
      gap: 2px;
      z-index: 90;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.92);
      max-height: 290px;
      overflow-y: auto;
    }''',
'''    .queue-menu {
      position: absolute;
      top: calc(100% + 4px);
      left: 0;
      width: 100%;
      min-width: 104px;
      background: #11151e;
      border: 1px solid #2b3240;
      border-radius: 12px;
      padding: 4px;
      display: none;
      flex-direction: column;
      gap: 2px;
      z-index: 90;
      box-shadow: 0 12px 30px rgba(0, 0, 0, 0.95);
    }'''
)

html = html.replace(
'''    .queue-opt {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 5px 8px;
      border-radius: 7px;
      font-size: 12.5px;
      font-weight: 700;
      color: #e5e7eb;
      cursor: pointer;
    }''',
'''    .queue-opt {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 6.5px 10px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 700;
      color: #e5e7eb;
      cursor: pointer;
    }'''
)

# 4. Insert Support & VIP buttons bar and VIP/Donate Modals into HTML
old_bot_promo = '''    <!-- Telegram Bot Promo Link (Visible when opened in regular web browser) -->
    <a class="bot-promo-btn" id="botPromoBtn" href="https://t.me/svitlo_uz_bot" target="_blank" rel="noopener">
      <span>🔔 Сповіщення про відключення у Telegram</span>
      <span class="bot-promo-cta">Відкрити бот ↗</span>
    </a>'''

new_support_and_promo = '''    <!-- VIP & Donate Action Row -->
    <div class="support-bar">
      <button class="sup-btn vip" id="openVipModalBtn" type="button">⭐ Без реклами • 30 грн/міс</button>
      <button class="sup-btn donate" id="openDonateModalBtn" type="button">☕ На каву / Розвиток</button>
    </div>

    <!-- Telegram Bot Promo Link (Visible when opened in regular web browser) -->
    <a class="bot-promo-btn" id="botPromoBtn" href="https://t.me/svitlo_uz_bot" target="_blank" rel="noopener">
      <span>🔔 Сповіщення про відключення у Telegram</span>
      <span class="bot-promo-cta">Відкрити бот ↗</span>
    </a>'''

assert old_bot_promo in html
html = html.replace(old_bot_promo, new_support_and_promo, 1)

# Add VIP Modal and Donate Modal right before <script>
vip_donate_modals = '''
  <!-- VIP Subscription Modal -->
  <div class="modal-overlay" id="vipModal">
    <div class="modal-box">
      <div class="modal-header">
        <div>
          <div class="modal-title">⭐ VIP без реклами • 30 днів</div>
          <div class="modal-sub">Користуйтеся графіком чисто та без банерів</div>
        </div>
        <button class="modal-close" id="vipCloseBtn" aria-label="Закрити">✕</button>
      </div>
      <div class="modal-body">
        <div id="vipStatusBanner" class="adm-card" style="display:none; border-color:rgba(34,197,94,0.45);">
          <div style="font-size:12.5px; font-weight:800; color:#4ade80;" id="vipStatusText">✅ VIP активовано</div>
        </div>

        <div class="adm-card">
          <div style="font-size:12px; font-weight:700; color:#f3f4f6;">Що входить у підписку (30 грн / 30 днів):</div>
          <div class="pay-note">
            • Повне відключення всієї реклами на 30 днів<br>
            • Підтримка стабільної роботи сервера та парсера УЗ<br>
            • Ваш ID у системі: <b style="color:#38bdf8;" id="vipUserIdDisplay">—</b>
          </div>
        </div>

        <div class="pay-card-box">
          <div style="font-size:11px; font-weight:700; color:#94a3b8;">Переказ на картку Монобанк (30 грн):</div>
          <div class="pay-card-num">4874 0700 5487 2484</div>
          <button class="pay-copy-btn" id="copyVipCardBtn" type="button">📋 Скопіювати номер картки</button>
        </div>

        <a class="pay-cta-link" id="vipConfirmTgLink" href="https://t.me/smm303" target="_blank" rel="noopener">
          ✅ Я оплатив 30 грн (написати адміну) ↗
        </a>
        <div class="pay-note" style="text-align:center;">
          Після переказу натисніть кнопку вище — адмін активує VIP на 30 днів по вашому ID.
        </div>
      </div>
    </div>
  </div>

  <!-- Donate / Coffee Modal -->
  <div class="modal-overlay" id="donateModal">
    <div class="modal-box">
      <div class="modal-header">
        <div>
          <div class="modal-title">☕ Подяка автору та розвиток</div>
          <div class="modal-sub">Підтримайте проєкт «Світло УЗ»</div>
        </div>
        <button class="modal-close" id="donateCloseBtn" aria-label="Закрити">✕</button>
      </div>
      <div class="modal-body">
        <div class="adm-card">
          <div class="pay-note" style="color:#e2e8f0; font-size:11.5px;">
            Сервіс працює безкоштовно, щоб ви завжди знали точний час світла. Чим більше вашої підтримки — тим швидше ми додамо нові міста, зручні функції та миттєві сповіщення в бот!
          </div>
        </div>

        <div style="font-size:11px; font-weight:700; color:#94a3b8; padding:0 2px;">Оберіть комфортну суму подяки:</div>
        <div class="donate-amounts" id="donateAmounts">
          <button class="amt-chip" type="button" data-amt="20 грн">☕ 20 грн</button>
          <button class="amt-chip active" type="button" data-amt="50 грн">⚡ 50 грн</button>
          <button class="amt-chip" type="button" data-amt="100 грн">🔋 100 грн</button>
          <button class="amt-chip" type="button" data-amt="свою суму">❤️ Своя</button>
        </div>

        <div class="pay-card-box">
          <div style="font-size:11px; font-weight:700; color:#94a3b8;">Картка Монобанк для подяки (<span id="selectedDonateAmtLbl" style="color:#38bdf8;">50 грн</span>):</div>
          <div class="pay-card-num">4874 0700 5487 2484</div>
          <button class="pay-copy-btn" id="copyDonateCardBtn" type="button">📋 Скопіювати номер картки</button>
        </div>

        <a class="pay-cta-link blue" id="donateTgThanksLink" href="https://t.me/smm303" target="_blank" rel="noopener">
          💬 Написати подяку автору (@smm303) ↗
        </a>
      </div>
    </div>
  </div>
'''

html = html.replace('  <script>', vip_donate_modals + '\n  <script>', 1)

# 5. Update Admin Panel VIP section and stats to include Bot Subscribers & 30-day VIP timer
old_adm_split = '''        <div class="adm-split-stats">
          <div class="adm-pill-stat">
            <span>🤖 З Telegram-бота:</span>
            <span id="admTgCount" style="color:#38bdf8;">0</span>
          </div>
          <div class="adm-pill-stat">
            <span>🌐 З веб-сайту:</span>
            <span id="admWebCount" style="color:#4ade80;">0</span>
          </div>
        </div>'''

new_adm_split = '''        <div class="adm-split-stats">
          <div class="adm-pill-stat">
            <span>🤖 Через бот:</span>
            <span id="admTgCount" style="color:#38bdf8;">0</span>
          </div>
          <div class="adm-pill-stat">
            <span>🌐 Через сайт:</span>
            <span id="admWebCount" style="color:#4ade80;">0</span>
          </div>
        </div>
        <div class="adm-pill-stat" style="font-size:11px; font-weight:700;">
          <span>📣 Натиснули /start у боті (усього):</span>
          <span id="admBotSubsCount" style="color:#fbbf24;">0</span>
        </div>'''

assert old_adm_split in html
html = html.replace(old_adm_split, new_adm_split, 1)

old_adm_vip_card = '''        <div class="adm-card">
          <div class="adm-card-title">
            <span>⭐ VIP без реклами (по Telegram ID)</span>
          </div>
          <div class="adm-row">
            <input class="adm-input" id="admVipInput" placeholder="Введіть Telegram ID..." inputmode="numeric" />
            <button class="adm-btn" id="admAddVipBtn">Додати</button>
          </div>
          <div class="vip-chips" id="admVipList"></div>
        </div>'''

new_adm_vip_card = '''        <div class="adm-card">
          <div class="adm-card-title">
            <span>⭐ VIP на 30 днів (по ID користувача)</span>
          </div>
          <div class="adm-row">
            <input class="adm-input" id="admVipInput" placeholder="Введіть ID (напр. 549556547)..." />
            <button class="adm-btn" id="admAddVipBtn">+30 днів</button>
          </div>
          <div class="vip-chips" id="admVipList"></div>
        </div>'''

assert old_adm_vip_card in html
html = html.replace(old_adm_vip_card, new_adm_vip_card, 1)

# 6. Update JS: VIP 30-day timer logic, Monetag Telegram Mini App SDK (12348913) + Web Vignette (12347638), Modals & Copy buttons
old_monetag_and_vip_js = '''    let monetagLoaded = false;
    function loadMonetagAds() {
      if (monetagLoaded) return;
      monetagLoaded = true;
      (function(s) {
        s.dataset.zone = "12347638";
        s.src = "https://n6wxm.com/vignette.min.js";
      })([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement("script")));
      (function(s) {
        s.dataset.zone = "12347928";
        s.src = "https://nap5k.com/tag.min.js";
      })([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement("script")));
    }

    function applyAdVisibility() {
      const adWrap = document.getElementById("adWrapper");
      const bottomSlot = document.getElementById("adBottomSlot");
      const bannerEl = document.getElementById("customAdBanner");
      const bannerText = document.getElementById("customAdText");

      const isVip = Boolean(remoteConfig.vip && remoteConfig.vip[currentUser.id]);
      const hideAds = !previewAsRegular && (isAdminUser || isVip);

      if (hideAds) {
        adWrap.style.display = "none";
        bottomSlot.style.display = "none";
        return;
      }

      loadMonetagAds();
      bottomSlot.style.display = "flex";

      const b = remoteConfig.banner || {};
      if (b.enabled === false) {
        adWrap.style.display = "none";
        return;
      }

      bannerText.textContent = b.text || "Місце для вашої реклами у Тернополі";
      bannerEl.href = b.url || "https://t.me/smm303";
      adWrap.style.display = "flex";
    }'''

new_monetag_and_vip_js = '''    const MONO_CARD_RAW = "4874070054872484";
    const VIP_DURATION_MS = 30 * 24 * 60 * 60 * 1000;

    function getVipEntryInfo(entry) {
      if (!entry) return { active: false, label: "" };
      if (entry === true) return { active: true, label: "назавжди" };
      if (typeof entry === "object" && entry.until) {
        const now = Date.now();
        if (now >= entry.until) return { active: false, label: "закінчився" };
        const d = new Date(entry.until);
        const daysLeft = Math.max(1, Math.ceil((entry.until - now) / (24 * 60 * 60 * 1000)));
        const dateStr = `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}`;
        return { active: true, label: `до ${dateStr} (${daysLeft} дн.)`, until: entry.until };
      }
      return { active: false, label: "" };
    }

    function isCurrentUserVip() {
      if (!remoteConfig.vip || !currentUser.id) return false;
      return getVipEntryInfo(remoteConfig.vip[currentUser.id]).active;
    }

    function updateVipButtonState() {
      const btn = document.getElementById("openVipModalBtn");
      const statusBox = document.getElementById("vipStatusBanner");
      const statusTxt = document.getElementById("vipStatusText");
      const info = remoteConfig.vip ? getVipEntryInfo(remoteConfig.vip[currentUser.id]) : { active: false };

      if (info.active) {
        btn.classList.add("active-vip");
        btn.textContent = `⭐ VIP активний (${info.label})`;
        statusBox.style.display = "block";
        statusTxt.textContent = `✅ Ваш VIP без реклами активний ${info.label}`;
      } else {
        btn.classList.remove("active-vip");
        btn.textContent = "⭐ Без реклами • 30 грн/міс";
        statusBox.style.display = "none";
      }
    }

    let monetagWebLoaded = false;
    let monetagTmaTriggered = false;

    function isInsideTelegramApp() {
      const tg = window.Telegram && window.Telegram.WebApp;
      return Boolean(tg && tg.initData && tg.initData.length > 0);
    }

    function triggerMonetagTmaAd(attempt = 0) {
      if (monetagTmaTriggered) return;
      if (typeof window.show_12348913 === "function") {
        monetagTmaTriggered = true;
        try {
          window.show_12348913({
            type: "inApp",
            inAppSettings: {
              frequency: 1,
              capping: 0.1,
              interval: 60,
              timeout: 3,
              everyPage: false
            }
          }).catch(() => {});
        } catch (e) {}
      } else if (attempt < 10) {
        setTimeout(() => triggerMonetagTmaAd(attempt + 1), 600);
      }
    }

    function loadMonetagAds() {
      if (isInsideTelegramApp()) {
        // Telegram Mini App Zone (12348913)
        triggerMonetagTmaAd(0);
      } else {
        // Regular Web Browser Vignette Zone (12347638)
        if (!monetagWebLoaded) {
          monetagWebLoaded = true;
          (function(s) {
            s.dataset.zone = "12347638";
            s.src = "https://n6wxm.com/vignette.min.js";
          })([document.documentElement, document.body].filter(Boolean).pop().appendChild(document.createElement("script")));
        }
      }
    }

    function applyAdVisibility() {
      const adWrap = document.getElementById("adWrapper");
      const bottomSlot = document.getElementById("adBottomSlot");
      const bannerEl = document.getElementById("customAdBanner");
      const bannerText = document.getElementById("customAdText");

      updateVipButtonState();

      const isVip = isCurrentUserVip();
      const hideAds = !previewAsRegular && (isAdminUser || isVip);

      if (hideAds) {
        adWrap.style.display = "none";
        bottomSlot.style.display = "none";
        return;
      }

      loadMonetagAds();
      bottomSlot.style.display = "flex";

      const b = remoteConfig.banner || {};
      if (b.enabled === false) {
        adWrap.style.display = "none";
        return;
      }

      bannerText.textContent = b.text || "Місце для вашої реклами у Тернополі";
      bannerEl.href = b.url || "https://t.me/smm303";
      adWrap.style.display = "flex";
    }'''

assert old_monetag_and_vip_js in html
html = html.replace(old_monetag_and_vip_js, new_monetag_and_vip_js, 1)

# 7. Update Admin Dashboard & VIP management functions for 30-day timer + bot_subscribers count
old_admin_js = '''        const [presenceMap, todayMap, usersMap, viewsToday] = await Promise.all([
          fbGet("presence"),
          fbGet(`daily/${k.isoDay}`),
          fbGet("users"),
          fbGet(`views/${k.isoDay}`)
        ]);

        const now = Date.now();
        const onlineCount = presenceMap
          ? Object.values(presenceMap).filter((x) => x && now - x.ts < 55000).length
          : 0;
        const todayList = todayMap ? Object.values(todayMap) : [];
        const usersArr = usersMap ? Object.values(usersMap) : [];

        const tgToday = todayList.filter((x) => x && x.source === "telegram").length;
        const webToday = todayList.filter((x) => x && x.source !== "telegram").length;

        document.getElementById("admOnlineVal").textContent = onlineCount;
        document.getElementById("admTodayVal").textContent = todayList.length;
        document.getElementById("admViewsVal").textContent = viewsToday || todayList.length;
        document.getElementById("admTotalVal").textContent = usersArr.length;
        document.getElementById("admTgCount").textContent = tgToday;
        document.getElementById("admWebCount").textContent = webToday;

        usersArr.sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0));
        const listEl = document.getElementById("admUsersList");
        if (usersArr.length === 0) {
          listEl.innerHTML = `<div class="adm-user-meta">Поки немає записів</div>`;
        } else {
          listEl.innerHTML = usersArr.slice(0, 50).map((u) => {
            const isTg = u.source === "telegram";
            const badge = isTg
              ? `<span class="adm-src-badge tg">TG</span>`
              : `<span class="adm-src-badge web">WEB</span>`;
            const vipBtn = isTg
              ? `<button class="adm-btn secondary" style="padding:3px 7px; font-size:10px;" onclick="quickAddVip('${u.id}')">+VIP</button>`
              : ``;
            return `
              <div class="adm-user-item">
                <div>
                  <div style="font-weight:700; color:#fff;">
                    ${u.name || "Відвідувач"} <span style="color:var(--blue)">${u.username || ""}</span> ${badge}
                  </div>
                  <div class="adm-user-meta">
                    📍 ${u.city || "Україна"} • ⚡ ${u.queue || "6(1)"} • 📱 ${u.device || ""}
                  </div>
                  <div class="adm-user-meta">
                    ID: ${u.id} • 🕒 ${u.last_seen_str || ""}
                  </div>
                </div>
                ${vipBtn}
              </div>
            `;
          }).join("");
        }
      } catch (e) {}
    }

    function renderVipChips() {
      const box = document.getElementById("admVipList");
      const ids = Object.keys(remoteConfig.vip || {}).filter((id) => remoteConfig.vip[id]);
      if (ids.length === 0) {
        box.innerHTML = `<span class="adm-user-meta">Список VIP порожній (твій ID вже без реклами)</span>`;
        return;
      }
      box.innerHTML = ids.map((id) => `
        <span class="vip-chip">
          <span>${id}</span>
          <button class="adm-btn danger" onclick="removeVip('${id}')">✕</button>
        </span>
      `).join("");
    }

    window.quickAddVip = async function(id) {
      if (!id) return;
      remoteConfig.vip[id] = true;
      await fbPut(`config/vip/${id}`, true);
      renderVipChips();
      applyAdVisibility();
    };

    window.removeVip = async function(id) {
      delete remoteConfig.vip[id];
      await fbPut(`config/vip/${id}`, null);
      renderVipChips();
      applyAdVisibility();
    };'''

new_admin_js = '''        const [presenceMap, todayMap, usersMap, viewsToday, botSubsMap] = await Promise.all([
          fbGet("presence"),
          fbGet(`daily/${k.isoDay}`),
          fbGet("users"),
          fbGet(`views/${k.isoDay}`),
          fbGet("bot_subscribers")
        ]);

        const now = Date.now();
        const onlineCount = presenceMap
          ? Object.values(presenceMap).filter((x) => x && now - x.ts < 55000).length
          : 0;
        const todayList = todayMap ? Object.values(todayMap) : [];
        const usersArr = usersMap ? Object.values(usersMap) : [];
        const botSubsCount = botSubsMap ? Object.keys(botSubsMap).length : 0;

        const tgToday = todayList.filter((x) => x && x.source === "telegram").length;
        const webToday = todayList.filter((x) => x && x.source !== "telegram").length;

        document.getElementById("admOnlineVal").textContent = onlineCount;
        document.getElementById("admTodayVal").textContent = todayList.length;
        document.getElementById("admViewsVal").textContent = viewsToday || todayList.length;
        document.getElementById("admTotalVal").textContent = usersArr.length;
        document.getElementById("admTgCount").textContent = tgToday;
        document.getElementById("admWebCount").textContent = webToday;
        document.getElementById("admBotSubsCount").textContent = botSubsCount;

        usersArr.sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0));
        const listEl = document.getElementById("admUsersList");
        if (usersArr.length === 0) {
          listEl.innerHTML = `<div class="adm-user-meta">Поки немає записів</div>`;
        } else {
          listEl.innerHTML = usersArr.slice(0, 50).map((u) => {
            const isTg = u.source === "telegram";
            const badge = isTg
              ? `<span class="adm-src-badge tg">TG</span>`
              : `<span class="adm-src-badge web">WEB</span>`;
            const vipInfo = getVipEntryInfo(remoteConfig.vip && remoteConfig.vip[u.id]);
            const vipBtn = vipInfo.active
              ? `<button class="adm-btn secondary" style="padding:3px 7px; font-size:10px; color:#4ade80;" onclick="quickAddVip('${u.id}')">+30д ще</button>`
              : `<button class="adm-btn secondary" style="padding:3px 7px; font-size:10px;" onclick="quickAddVip('${u.id}')">+30д VIP</button>`;
            return `
              <div class="adm-user-item">
                <div>
                  <div style="font-weight:700; color:#fff;">
                    ${u.name || "Відвідувач"} <span style="color:var(--blue)">${u.username || ""}</span> ${badge}
                  </div>
                  <div class="adm-user-meta">
                    📍 ${u.city || "Україна"} • ⚡ ${u.queue || "6(1)"} • 📱 ${u.device || ""}
                  </div>
                  <div class="adm-user-meta">
                    ID: ${u.id} • 🕒 ${u.last_seen_str || ""}
                  </div>
                </div>
                ${vipBtn}
              </div>
            `;
          }).join("");
        }
      } catch (e) {}
    }

    function renderVipChips() {
      const box = document.getElementById("admVipList");
      const allIds = Object.keys(remoteConfig.vip || {});
      const activeIds = allIds.filter((id) => getVipEntryInfo(remoteConfig.vip[id]).active);

      // Clean up expired entries in background
      allIds.forEach((id) => {
        if (!getVipEntryInfo(remoteConfig.vip[id]).active) {
          delete remoteConfig.vip[id];
          fbPut(`config/vip/${id}`, null).catch(() => {});
        }
      });

      if (activeIds.length === 0) {
        box.innerHTML = `<span class="adm-user-meta">Активних VIP поки немає (твій ID вже без реклами)</span>`;
        return;
      }
      box.innerHTML = activeIds.map((id) => {
        const info = getVipEntryInfo(remoteConfig.vip[id]);
        return `
          <span class="vip-chip">
            <span>${id} • ${info.label}</span>
            <button class="adm-btn secondary" style="padding:2px 6px; font-size:10px;" onclick="quickAddVip('${id}')" title="Продовжити на 30 днів">+30д</button>
            <button class="adm-btn danger" onclick="removeVip('${id}')">✕</button>
          </span>
        `;
      }).join("");
    }

    window.quickAddVip = async function(id) {
      if (!id) return;
      const existing = remoteConfig.vip && remoteConfig.vip[id];
      const baseTime = (existing && typeof existing === "object" && existing.until && existing.until > Date.now())
        ? existing.until
        : Date.now();
      const untilTs = baseTime + VIP_DURATION_MS;
      const d = new Date(untilTs);
      const entry = {
        until: untilTs,
        until_str: `${pad2(d.getDate())}.${pad2(d.getMonth() + 1)}.${d.getFullYear()}`
      };
      remoteConfig.vip[id] = entry;
      await fbPut(`config/vip/${id}`, entry);
      renderVipChips();
      applyAdVisibility();
    };

    window.removeVip = async function(id) {
      delete remoteConfig.vip[id];
      await fbPut(`config/vip/${id}`, null);
      renderVipChips();
      applyAdVisibility();
    };'''

assert old_admin_js in html
html = html.replace(old_admin_js, new_admin_js, 1)

# 8. Allow alphanumeric IDs (both Telegram numeric IDs and web_xxxx IDs) in admAddVipBtn + wire VIP & Donate modals
old_vip_btn_listener = '''    document.getElementById("admAddVipBtn").addEventListener("click", async () => {
      const inp = document.getElementById("admVipInput");
      const val = inp.value.trim().replace(/\\D/g, "");
      if (!val) return;
      inp.value = "";
      await window.quickAddVip(val);
    });'''

new_vip_donate_listeners = '''    document.getElementById("admAddVipBtn").addEventListener("click", async () => {
      const inp = document.getElementById("admVipInput");
      const val = inp.value.trim().replace(/[^a-zA-Z0-9_-]/g, "");
      if (!val) return;
      inp.value = "";
      await window.quickAddVip(val);
    });

    function copyCardNumber(btnEl) {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(MONO_CARD_RAW).catch(() => {});
      } else {
        const ta = document.createElement("textarea");
        ta.value = MONO_CARD_RAW;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      }
      const orig = btnEl.textContent;
      btnEl.classList.add("copied");
      btnEl.textContent = "✅ Номер картки скопійовано!";
      setTimeout(() => {
        btnEl.classList.remove("copied");
        btnEl.textContent = orig;
      }, 2200);
    }

    const vipModal = document.getElementById("vipModal");
    document.getElementById("openVipModalBtn").addEventListener("click", () => {
      document.getElementById("vipUserIdDisplay").textContent = currentUser.id || "—";
      const msg = encodeURIComponent(`Привіт! Оплатив 30 грн за VIP без реклами (30 днів) у Світло УЗ. Мій ID: ${currentUser.id}`);
      document.getElementById("vipConfirmTgLink").href = `https://t.me/smm303?text=${msg}`;
      updateVipButtonState();
      vipModal.classList.add("open");
    });
    document.getElementById("vipCloseBtn").addEventListener("click", () => vipModal.classList.remove("open"));
    vipModal.addEventListener("click", (e) => { if (e.target === vipModal) vipModal.classList.remove("open"); });
    document.getElementById("copyVipCardBtn").addEventListener("click", function() { copyCardNumber(this); });

    const donateModal = document.getElementById("donateModal");
    let selectedDonateAmt = "50 грн";
    function updateDonateLinks() {
      document.getElementById("selectedDonateAmtLbl").textContent = selectedDonateAmt;
      const msg = encodeURIComponent(`Привіт! Дякую за Світло УЗ ⚡ Підтримав проєкт на ${selectedDonateAmt}!`);
      document.getElementById("donateTgThanksLink").href = `https://t.me/smm303?text=${msg}`;
    }
    document.getElementById("openDonateModalBtn").addEventListener("click", () => {
      updateDonateLinks();
      donateModal.classList.add("open");
    });
    document.getElementById("donateCloseBtn").addEventListener("click", () => donateModal.classList.remove("open"));
    donateModal.addEventListener("click", (e) => { if (e.target === donateModal) donateModal.classList.remove("open"); });
    document.getElementById("copyDonateCardBtn").addEventListener("click", function() { copyCardNumber(this); });

    document.querySelectorAll("#donateAmounts .amt-chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        document.querySelectorAll("#donateAmounts .amt-chip").forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        selectedDonateAmt = chip.getAttribute("data-amt") || "50 грн";
        updateDonateLinks();
      });
    });'''

assert old_vip_btn_listener in html
html = html.replace(old_vip_btn_listener, new_vip_donate_listeners, 1)

with open("index_updated.html", "w", encoding="utf-8") as f:
    f.write(html)

assert "show_12348913" in html
assert "4874 0700 5487 2484" in html
assert "VIP_DURATION_MS" in html
print("OK index_updated.html:", len(html))