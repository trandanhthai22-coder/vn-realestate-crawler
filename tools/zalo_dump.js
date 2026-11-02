/* ============================================================================
   ZALO WEB - TRICH XUAT TIN NHAN THEO KHOANG NGAY
   ----------------------------------------------------------------------------
   CACH DUNG:
     1. Mo https://chat.zalo.me tren Chrome, vao dung nhom can lay tin.
     2. F12 -> tab Console -> dan TOAN BO file nay -> Enter.
     3. Script tu cuon nguoc len toi FROM_DATE, vua cuon vua thu thap,
        xong tai ve file zalo_messages.json.
     4. Dua file JSON do cho zalo_parse.py.

   DUNG GIUA CHUNG: go  __zaloStop = true  roi Enter (script se xuat phan da co).

   CHINH KHOANG NGAY o 2 dong FROM_DATE / TO_DATE ngay ben duoi.
============================================================================ */
(async () => {
  const FROM_DATE = "2026-08-13";   // lay tu ngay nay (00:00)
  const TO_DATE = null;             // null = toi hien tai; hoac "2026-08-20"
  const MAX_MINUTES = 25;           // tran thoi gian an toan

  const fromTs = new Date(FROM_DATE + "T00:00:00").getTime();
  const toTs = TO_DATE ? new Date(TO_DATE + "T23:59:59").getTime() : Date.now();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const vn = ts => new Date(ts).toLocaleString("vi-VN");

  window.__zaloStop = false;

  // --- Tim khung cuon cua danh sach tin nhan ---------------------------------
  function findScroller() {
    const anyMsg = document.querySelector('[id^="bb_msg_id_"]');
    if (!anyMsg) return null;
    let el = anyMsg.parentElement;
    while (el && el !== document.body) {
      const s = getComputedStyle(el);
      if (/(auto|scroll)/.test(s.overflowY) && el.scrollHeight > el.clientHeight + 50) return el;
      el = el.parentElement;
    }
    return null;
  }

  const scroller = findScroller();
  if (!scroller) {
    console.error("[zalo] Khong tim thay khung chat. Mo dung cuoc tro chuyen roi chay lai.");
    return;
  }

  // ID co 2 dang: 'bb_msg_id_<ts>' hoac 'bb_msg_id_<ts>_<uid>_g<groupid>'
  const tsOf = el => {
    const m = /^bb_msg_id_(\d{10,})/.exec(el.id || "");
    return m ? +m[1] : NaN;
  };

  // --- Thu thap tin dang hien tren DOM ---------------------------------------
  // QUAN TRONG: Zalo dung virtual scrolling - cuon len thi tin MOI bi go khoi
  // DOM. Nen phai gom lien tuc moi vong cuon, khong the doi den cuoi.
  const store = new Map();          // key: id day du cua node
  let lastSender = "";              // Zalo an ten khi nhieu tin lien tiep cung nguoi

  function harvest() {
    for (const node of document.querySelectorAll('[id^="bb_msg_id_"]')) {
      const ts = tsOf(node);
      if (!Number.isFinite(ts)) continue;

      const item = node.closest(".chat-item") || node;

      const nameEl = item.querySelector(".message-sender-name-content .truncate");
      const sender = nameEl ? nameEl.innerText.replace(/ /g, " ").trim() : "";
      if (sender) lastSender = sender;

      if (store.has(node.id)) continue;   // da gom roi

      const textEl = node.querySelector('[data-component="message-text-content"]');
      const text = textEl
        ? textEl.innerText.replace(/ /g, " ").replace(/\r\n/g, "\n").trim()
        : "";

      // Anh don (Msg_Photo) lan album nhieu anh (Msg_GrpPhoto), ca gui lan nhan
      const hasImage = !!node.querySelector(
        '[data-id*="Msg_Photo"], [data-id*="Msg_GrpPhoto"], ' +
        '.photo-message-v2, .img-msg-v2, .group-photo-message');

      if (!text && !hasImage) continue;
      if (ts < fromTs || ts > toTs) continue;

      const isMine = !!node.querySelector('[data-id*="_SentMsg_"]') ||
                     (item.className || "").includes("--send");

      store.set(node.id, {
        msg_id: String(ts),
        ts_ms: ts,
        datetime: new Date(ts).toISOString(),
        sender: sender || lastSender,
        text,
        has_image: hasImage,
        is_mine: isMine,
      });
    }
  }

  const oldestOnScreen = () => {
    const ids = [...document.querySelectorAll('[id^="bb_msg_id_"]')]
      .map(tsOf).filter(Number.isFinite);
    return ids.length ? Math.min(...ids) : Infinity;
  };

  // --- Buoc 1: ve day cuoc tro chuyen (tin moi nhat) -------------------------
  console.log("[zalo] Ve cuoi hoi thoai...");
  scroller.scrollTop = scroller.scrollHeight;
  await sleep(1200);
  harvest();

  // --- Buoc 2: cuon nguoc tung man hinh, vua cuon vua gom --------------------
  console.log("[zalo] Bat dau cuon nguoc toi " + FROM_DATE + " ...");
  const deadline = Date.now() + MAX_MINUTES * 60000;
  let stagnant = 0, prevOldest = Infinity, rounds = 0;

  while (Date.now() < deadline) {
    rounds++;
    if (window.__zaloStop) { console.warn("[zalo] Da dung theo yeu cau."); break; }

    harvest();

    const oldest = oldestOnScreen();
    if (Number.isFinite(oldest) && oldest <= fromTs) {
      console.log("[zalo] Da cham moc " + FROM_DATE + ".");
      break;
    }

    if (scroller.scrollTop > 0) {
      // Cuon tung buoc < 1 man hinh de moi tin deu di qua vung render,
      // tranh nhay coc lam sot tin o giua.
      scroller.scrollTop = Math.max(0, scroller.scrollTop - scroller.clientHeight * 0.8);
      await sleep(200);
    } else {
      // Da o dinh: cho Zalo tai them lich su cu hon
      await sleep(700);
    }

    // Ket thuc khi tin cu nhat khong lui them duoc nua
    if (oldest === prevOldest && scroller.scrollTop === 0) stagnant++;
    else stagnant = 0;
    prevOldest = oldest;

    if (stagnant >= 15) {
      console.warn("[zalo] Khong tai them duoc nua - co le da het lich su nhom.");
      break;
    }

    if (rounds % 15 === 0) {
      console.log(`[zalo] ...da gom ${store.size} tin | dang o moc: ` +
                  (Number.isFinite(oldest) ? vn(oldest) : "?"));
    }
  }

  harvest();   // gom lan cuoi

  // --- Buoc 3: xuat ----------------------------------------------------------
  const msgs = [...store.values()].sort((a, b) => a.ts_ms - b.ts_ms);
  const withText = msgs.filter(m => m.text);

  console.log(`[zalo] XONG: ${msgs.length} tin trong khoang (${withText.length} tin co chu).`);
  if (msgs.length) {
    console.log("  Som nhat :", vn(msgs[0].ts_ms));
    console.log("  Muon nhat:", vn(msgs[msgs.length - 1].ts_ms));
    const byDay = {};
    for (const m of msgs) {
      const d = new Date(m.ts_ms).toLocaleDateString("vi-VN");
      byDay[d] = (byDay[d] || 0) + 1;
    }
    console.table(byDay);
  } else {
    console.warn("[zalo] Khong co tin nao trong khoang ngay yeu cau.");
  }

  const payload = {
    exported_at: new Date().toISOString(),
    conversation: document.title,
    from_date: FROM_DATE,
    to_date: TO_DATE,
    count: msgs.length,
    messages: msgs,
  };

  window.__zaloMessages = msgs;          // du phong neu trinh duyet chan tai
  window.__zaloPayload = payload;

  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "zalo_messages.json";
  document.body.appendChild(a);
  a.click();
  a.remove();
  console.log("[zalo] Da tai zalo_messages.json ve thu muc Downloads.");
  console.log("[zalo] Neu khong thay file, go:  copy(JSON.stringify(__zaloPayload))");
})();
