/* Мини-апп «Расписание пар». Полностью статический: сам обращается к Google
   Sheets API и повторяет логику разбора из schedule_parser.py (Python-бота). */

const CONFIG = {
  SPREADSHEET_ID: "1kgwKRON2tOFtIgcf0OeoHC3WhT6H4s9F4sEtsgYBVbA",
  // Ключ read-only, ограничен только Google Sheets API — таблица открыта на просмотр всем.
  GOOGLE_API_KEY: "AIzaSyAAjCdh31z0AZMQk-fkH4K_iv2di6lePEU",
  DAYS: 7, // мини-апп всегда открывается на неделю вперёд
  CACHE_TTL_MS: 5 * 60 * 1000,
};

const FIELDS_MASK =
  "sheets(properties(sheetId,title,index),merges,data.rowData.values.formattedValue)";

const DAY_LABELS = ["ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС"];
const DAY_NAMES_FULL = {
  ПН: "Понедельник",
  ВТ: "Вторник",
  СР: "Среда",
  ЧТ: "Четверг",
  ПТ: "Пятница",
  СБ: "Суббота",
  ВС: "Воскресенье",
};

const TYPE_RE = /^\[(Л|С|ПЗ)\]\s*(.*)$/;
// JS-овский \b не Unicode-осведомлён (не считает кириллицу "словом"), поэтому
// границы делаем через lookaround вручную — иначе главную роль эквивалентная
// Python-регулярка (там \b работает с юникодом) сыграла бы иначе.
const ROOM_RE = /(?<![A-Za-zА-Яа-я0-9])([А-ЯA-Z]{1,2}-?\d{3})(?![A-Za-zА-Яа-я0-9])/;
const URL_RE = /https?:\/\/[^\s)\]]+/;
const NOT_STARTED_RE = /2-?[ег]?о?\s*модул/i;
const SKIP_SLOT_RE = /НЕ\s+ВЫБИРАТЬ/i;
const START_DATE_RE = /^[CС]\s*(\d{1,2})\.(\d{2})\.?$/;
const ONLY_DATES_LINE_RE = /^\d{1,2}\.\d{2}(\s*,\s*\d{1,2}\.\d{2})*\.?$/;
const DATE_TOKEN_RE = /(\d{1,2})\.(\d{2})/g;
const RESCHEDULE_RE = /(\d{1,2})\.(\d{2})\s+перенос(?:[^\d(){}[\]]*)(\d{1,2})[.:](\d{2})/gi;
const ONLINE_MARK_RE = /^ОНЛАЙН$/i;

const TYPE_NAMES = { Л: "Лекция", С: "Семинар", ПЗ: "Практика" };
const TYPE_CSS_VAR = { Л: "--type-lecture", С: "--type-seminar", ПЗ: "--type-practice" };

const GROUP_RE = /^\d{3,4}-\d{1,2}$/;

// ---------------------------------------------------------------------------
// Загрузка данных таблицы
// ---------------------------------------------------------------------------

async function fetchTabs() {
  const url =
    `https://sheets.googleapis.com/v4/spreadsheets/${CONFIG.SPREADSHEET_ID}` +
    `?key=${CONFIG.GOOGLE_API_KEY}&fields=${encodeURIComponent(FIELDS_MASK)}`;
  const resp = await fetch(url);
  if (!resp.ok) {
    throw new Error(`Sheets API ${resp.status}`);
  }
  const payload = await resp.json();

  const tabs = [];
  for (const sheet of payload.sheets || []) {
    const props = sheet.properties || {};
    const grid = [];
    const dataBlocks = sheet.data || [];
    const rowData = dataBlocks.length ? dataBlocks[0].rowData || [] : [];
    for (const row of rowData) {
      const values = row.values || [];
      grid.push(values.map((v) => v.formattedValue || ""));
    }
    const merges = (sheet.merges || []).map((m) => [
      m.startRowIndex || 0,
      m.endRowIndex || 0,
      m.startColumnIndex || 0,
      m.endColumnIndex || 0,
    ]);
    tabs.push({ title: props.title || "", grid, merges });
  }
  return tabs;
}

function cellValue(tab, row, col) {
  const r = tab.grid[row];
  if (!r) return "";
  return r[col] || "";
}

function mergeAt(tab, row, col) {
  for (const m of tab.merges) {
    const [sr, er, sc, ec] = m;
    if (sr <= row && row < er && sc <= col && col < ec) return m;
  }
  return null;
}

function resolveCell(tab, row, col) {
  const val = cellValue(tab, row, col);
  if (val) return val;
  const merge = mergeAt(tab, row, col);
  if (merge) return cellValue(tab, merge[0], merge[2]);
  return "";
}

// ---------------------------------------------------------------------------
// Разбор ячеек (порт schedule_parser.py)
// ---------------------------------------------------------------------------

function parseTimeRange(label) {
  const m = label.trim().match(/(\d{1,2})[.:](\d{2})\s*-\s*(\d{1,2})[.:](\d{2})/);
  if (!m) return { display: label.trim(), startMinutes: 0, duration: 90 };
  const [, h1, m1, h2, m2] = m;
  const startMinutes = parseInt(h1, 10) * 60 + parseInt(m1, 10);
  const endMinutes = parseInt(h2, 10) * 60 + parseInt(m2, 10);
  const display = `${parseInt(h1, 10)}:${m1}–${parseInt(h2, 10)}:${m2}`;
  return { display, startMinutes, duration: Math.max(endMinutes - startMinutes, 0) };
}

function parseDateConstraints(restLines) {
  let excluded = false;
  let startDate = null; // [month, day]
  let onlyDates = null; // Set of "m-d"
  const reschedule = new Map(); // "m-d" -> [hour, minute]

  for (const line of restLines) {
    if (NOT_STARTED_RE.test(line) || SKIP_SLOT_RE.test(line)) {
      excluded = true;
    }

    const m = line.match(START_DATE_RE);
    if (m) {
      const day = parseInt(m[1], 10);
      const month = parseInt(m[2], 10);
      startDate = [month, day];
      continue;
    }

    if (ONLY_DATES_LINE_RE.test(line)) {
      const dates = new Set();
      let dm;
      DATE_TOKEN_RE.lastIndex = 0;
      while ((dm = DATE_TOKEN_RE.exec(line)) !== null) {
        const day = parseInt(dm[1], 10);
        const month = parseInt(dm[2], 10);
        dates.add(`${month}-${day}`);
      }
      if (dates.size) onlyDates = dates;
      continue;
    }

    let rm;
    RESCHEDULE_RE.lastIndex = 0;
    while ((rm = RESCHEDULE_RE.exec(line)) !== null) {
      const day = parseInt(rm[1], 10);
      const month = parseInt(rm[2], 10);
      const hour = parseInt(rm[3], 10);
      const minute = parseInt(rm[4], 10);
      reschedule.set(`${month}-${day}`, [hour, minute]);
    }
  }

  return { excluded, startDate, onlyDates, reschedule };
}

function parseCellText(text) {
  const lines = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l !== "");
  if (!lines.length) return null;

  const m = lines[0].match(TYPE_RE);
  if (!m) return null;
  const lessonType = m[1];
  const subject = m[2].trim();

  let teacher = lines.length > 1 ? lines[1].trim() : "";
  let isOnline = ONLINE_MARK_RE.test(teacher);
  if (isOnline) {
    teacher = "";
  } else if (lines.slice(2).some((ln) => ONLINE_MARK_RE.test(ln))) {
    isOnline = true;
  }

  const restLines = lines.slice(2);
  const rest = restLines.join("\n");
  const roomMatch = rest.match(ROOM_RE);
  const urlMatch = rest.match(URL_RE);
  const constraints = parseDateConstraints(restLines);

  return {
    type: lessonType,
    subject,
    teacher,
    room: roomMatch ? roomMatch[1] : null,
    url: urlMatch ? urlMatch[0] : null,
    isOnline,
    ...constraints,
  };
}

function findGroupColumn(tabs, group) {
  for (const tab of tabs) {
    for (let rowIdx = 0; rowIdx < tab.grid.length; rowIdx++) {
      const row = tab.grid[rowIdx];
      for (let colIdx = 0; colIdx < row.length; colIdx++) {
        const val = row[colIdx];
        if (val && val.trim() === group) {
          return { tab, headerRow: rowIdx, targetCol: colIdx };
        }
      }
    }
  }
  return null;
}

function instanceFor(tpl, date) {
  if (tpl.excluded) return null;
  const key = `${date.getMonth() + 1}-${date.getDate()}`;
  if (tpl.onlyDates !== null) {
    if (!tpl.onlyDates.has(key)) return null;
  } else if (tpl.startDate !== null) {
    const [sm, sd] = tpl.startDate;
    const cmpKey = [date.getMonth() + 1, date.getDate()];
    if (cmpKey[0] < sm || (cmpKey[0] === sm && cmpKey[1] < sd)) return null;
  }

  if (tpl.reschedule.has(key)) {
    const [h, mi] = tpl.reschedule.get(key);
    const newStart = h * 60 + mi;
    const newEnd = newStart + tpl.durationMinutes;
    const display = `${h}:${String(mi).padStart(2, "0")}–${Math.floor(newEnd / 60)}:${String(
      newEnd % 60
    ).padStart(2, "0")}`;
    return { display, startMinutes: newStart };
  }

  return { display: tpl.timeDisplay, startMinutes: tpl.startMinutes };
}

function templatesByDay(tabs, group) {
  const found = findGroupColumn(tabs, group);
  if (!found) return null;
  const { tab, headerRow, targetCol } = found;

  const result = {};
  for (const d of DAY_LABELS) result[d] = [];

  for (let r = headerRow + 1; r < tab.grid.length; r++) {
    const dayLabel = resolveCell(tab, r, 0).trim().toUpperCase();
    const timeLabel = (cellValue(tab, r, 1) || "").trim();
    if (!DAY_LABELS.includes(dayLabel) || !timeLabel) continue;

    const { display: timeDisplay, startMinutes, duration } = parseTimeRange(timeLabel);

    let cellText = cellValue(tab, r, targetCol);
    const merge = mergeAt(tab, r, targetCol);
    if (!cellText) {
      if (merge) cellText = cellValue(tab, merge[0], merge[2]);
      if (!cellText) continue;
    }

    const parsed = parseCellText(cellText);
    if (!parsed) continue;

    result[dayLabel].push({
      timeLabel,
      timeDisplay,
      startMinutes,
      durationMinutes: duration,
      lessonType: parsed.type,
      subject: parsed.subject,
      teacher: parsed.teacher,
      room: parsed.room,
      url: parsed.url,
      isOnline: parsed.isOnline,
      excluded: parsed.excluded,
      startDate: parsed.startDate,
      onlyDates: parsed.onlyDates,
      reschedule: parsed.reschedule,
    });
  }
  return result;
}

function buildSchedule(tabs, group, days, start) {
  const byDay = templatesByDay(tabs, group);
  if (!byDay) return null;

  const schedule = [];
  let d = new Date(start);
  while (schedule.length < days) {
    const label = DAY_LABELS[(d.getDay() + 6) % 7]; // JS: 0=Sunday -> сдвиг на ПН=0
    if (label === "ВС") {
      d = new Date(d.getTime() + 86400000);
      continue;
    }

    const lessons = [];
    for (const tpl of byDay[label] || []) {
      const instance = instanceFor(tpl, d);
      if (!instance) continue;
      lessons.push({
        timeDisplay: instance.display,
        startMinutes: instance.startMinutes,
        durationMinutes: tpl.durationMinutes,
        lessonType: tpl.lessonType,
        subject: tpl.subject,
        teacher: tpl.teacher,
        room: tpl.room,
        url: tpl.url,
        isOnline: tpl.isOnline,
      });
    }
    lessons.sort((a, b) => a.startMinutes - b.startMinutes);

    schedule.push({
      date: new Date(d),
      dayLabel: label,
      dayName: DAY_NAMES_FULL[label],
      lessons,
    });
    d = new Date(d.getTime() + 86400000);
  }
  return schedule;
}

// ---------------------------------------------------------------------------
// Рендер
// ---------------------------------------------------------------------------

function fmtDM(date) {
  return `${String(date.getDate()).padStart(2, "0")}.${String(date.getMonth() + 1).padStart(2, "0")}`;
}

function formatGap(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `Перерыв ${h}:${String(m).padStart(2, "0")}`;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function renderSchedule(schedule, group) {
  const content = document.getElementById("content");
  const dateRangeEl = document.getElementById("dateRange");
  const groupLabelEl = document.getElementById("groupLabel");

  const first = schedule[0].date;
  const last = schedule[schedule.length - 1].date;
  dateRangeEl.textContent = fmtDM(first) === fmtDM(last)
    ? fmtDM(first)
    : `${fmtDM(first)} – ${fmtDM(last)}`;
  groupLabelEl.textContent = `Группа ${group}`;

  const parts = [];
  for (const day of schedule) {
    parts.push(`<section class="day-block">`);
    parts.push(`<div class="day-pill">${escapeHtml(day.dayName)}, ${fmtDM(day.date)}</div>`);

    if (!day.lessons.length) {
      parts.push(`<div class="empty-day">Занятий нет</div>`);
    } else {
      let prevEnd = null;
      for (const lesson of day.lessons) {
        if (prevEnd !== null) {
          const gap = lesson.startMinutes - prevEnd;
          if (gap > 0) parts.push(`<div class="gap-text">${formatGap(gap)}</div>`);
        }
        prevEnd = lesson.startMinutes + lesson.durationMinutes;

        const colorVar = TYPE_CSS_VAR[lesson.lessonType] || "--type-lecture";
        let head = lesson.timeDisplay;
        if (lesson.room) head += `   ·   ${lesson.room}`;

        let badge = TYPE_NAMES[lesson.lessonType] || lesson.lessonType;
        if (lesson.isOnline) badge += "   ·   Онлайн";

        let teacherLine = lesson.teacher ? escapeHtml(lesson.teacher) : "—";
        if (lesson.url) {
          teacherLine += ` · <a href="${escapeHtml(lesson.url)}" target="_blank" rel="noopener">трансляция</a>`;
        }

        parts.push(
          `<div class="lesson-card" style="--bar-color: var(${colorVar})">` +
            `<p class="lesson-time">${escapeHtml(head)}</p>` +
            `<p class="lesson-badge">${escapeHtml(badge)}</p>` +
            `<p class="lesson-subject">${escapeHtml(lesson.subject)}</p>` +
            `<p class="lesson-teacher">${teacherLine}</p>` +
          `</div>`
        );
      }
    }
    parts.push(`</section>`);
  }
  content.innerHTML = parts.join("");
}

function renderStatus(text) {
  document.getElementById("content").innerHTML = `<div class="status-text">${escapeHtml(text)}</div>`;
}

// ---------------------------------------------------------------------------
// Тема
// ---------------------------------------------------------------------------

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.getElementById("themeBtn").textContent = theme === "dark" ? "☀️" : "🌙";
}

function initTheme() {
  let theme = localStorage.getItem("theme");
  if (!theme) {
    const tg = window.Telegram && window.Telegram.WebApp;
    theme = tg && tg.colorScheme === "dark" ? "dark" : "light";
  }
  applyTheme(theme);
}

document.getElementById("themeBtn").addEventListener("click", () => {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  localStorage.setItem("theme", next);
  applyTheme(next);
});

// ---------------------------------------------------------------------------
// Группа (модалка)
// ---------------------------------------------------------------------------

function getGroup() {
  return localStorage.getItem("group");
}

function showGroupModal(prefill) {
  const modal = document.getElementById("groupModal");
  const input = document.getElementById("groupInput");
  const error = document.getElementById("groupError");
  input.value = prefill || "";
  error.classList.add("hidden");
  modal.classList.remove("hidden");
  setTimeout(() => input.focus(), 50);
}

function hideGroupModal() {
  document.getElementById("groupModal").classList.add("hidden");
}

document.getElementById("changeGroupBtn").addEventListener("click", () => {
  showGroupModal(getGroup() || "");
});

document.getElementById("groupSaveBtn").addEventListener("click", () => {
  const input = document.getElementById("groupInput");
  const error = document.getElementById("groupError");
  const value = input.value.trim().replace(/\s+/g, "");
  if (!GROUP_RE.test(value)) {
    error.textContent = "Не похоже на номер группы. Пример: 2615-2";
    error.classList.remove("hidden");
    return;
  }
  localStorage.setItem("group", value);
  hideGroupModal();
  loadAndRender(false);
});

// ---------------------------------------------------------------------------
// Загрузка с кэшем (не чаще раза в 5 минут)
// ---------------------------------------------------------------------------

function readCache() {
  try {
    const raw = localStorage.getItem("scheduleCache");
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeCache(tabs) {
  localStorage.setItem("scheduleCache", JSON.stringify({ tabs, fetchedAt: Date.now() }));
}

function humanizeAgo(fetchedAt) {
  const seconds = Math.floor((Date.now() - fetchedAt) / 1000);
  if (seconds < 60) return "только что";
  const minutes = Math.floor(seconds / 60);
  if (minutes === 1) return "1 минуту назад";
  if (minutes >= 2 && minutes <= 4) return `${minutes} минуты назад`;
  return `${minutes} минут назад`;
}

let currentTabs = null;
let currentFetchedAt = 0;

function renderFromTabs(tabs) {
  const group = getGroup();
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const schedule = buildSchedule(tabs, group, CONFIG.DAYS, today);
  if (!schedule) {
    renderStatus(`Группа «${group}» не найдена в таблице. Проверьте номер.`);
    return;
  }
  renderSchedule(schedule, group);
}

async function loadAndRender(forceNetwork) {
  const group = getGroup();
  if (!group) {
    showGroupModal("");
    return;
  }

  const cache = readCache();
  const cacheAge = cache ? Date.now() - cache.fetchedAt : Infinity;
  const isFresh = cacheAge < CONFIG.CACHE_TTL_MS;

  if (cache && (isFresh || !forceNetwork)) {
    currentTabs = cache.tabs;
    currentFetchedAt = cache.fetchedAt;
    renderFromTabs(currentTabs);
  }

  if (!cache) renderStatus("Загрузка расписания…");

  if (cache && isFresh && forceNetwork) {
    // Explicit refresh, но кэш ещё свежий — не дёргаем API лишний раз.
    const leftMs = CONFIG.CACHE_TTL_MS - cacheAge;
    const leftMin = Math.max(1, Math.ceil(leftMs / 60000));
    flashNote(`Обновление не чаще раза в 5 минут. Ещё ${leftMin} мин.`);
    return;
  }

  try {
    const tabs = await fetchTabs();
    currentTabs = tabs;
    currentFetchedAt = Date.now();
    writeCache(tabs);
    renderFromTabs(tabs);
  } catch (e) {
    if (!cache) {
      renderStatus("Не удалось загрузить таблицу. Проверьте интернет-соединение и попробуйте ещё раз.");
    } else {
      flashNote("Не удалось обновить данные. Показано последнее сохранённое расписание.");
    }
  }
}

function flashNote(text) {
  document.querySelectorAll(".toast").forEach((el) => el.remove());
  const toast = document.createElement("div");
  toast.className = "toast";
  toast.textContent = text;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 3000);
}

document.getElementById("refreshBtn").addEventListener("click", (e) => {
  e.currentTarget.classList.remove("spin");
  void e.currentTarget.offsetWidth;
  e.currentTarget.classList.add("spin");
  loadAndRender(true);
});

// ---------------------------------------------------------------------------
// Инициализация
// ---------------------------------------------------------------------------

(function init() {
  const tg = window.Telegram && window.Telegram.WebApp;
  if (tg) {
    tg.ready();
    tg.expand();
  }
  initTheme();
  loadAndRender(false);
})();
