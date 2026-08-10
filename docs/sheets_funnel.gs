/**
 * Apps Script для воронки Telegram-бота (Федерация Здоровья).
 *
 * УСТАНОВКА
 * 1. Откройте таблицу, куда сейчас пишутся заказы -> Расширения -> Apps Script.
 * 2. Вставьте этот код РЯДОМ с существующим, но:
 *    - переименуйте текущую функцию doPost в handleOrder_(payload)
 *      (внутри она уже работает с полями platform/category/title/... —
 *       менять её тело не нужно, только имя и то, что аргумент приходит
 *       готовым объектом, а не e);
 *    - если старый doPost парсил e.postData.contents — эту строку из него уберите.
 * 3. Развернуть -> Управление развёртываниями -> Изменить -> Новая версия.
 *    URL остаётся прежним, SHEETS_SCRIPT_URL менять не нужно.
 *
 * Листы users / events / content создаются автоматически при первом запросе.
 */

var SECRET = 'ЗАМЕНИТЕ_НА_ЗНАЧЕНИЕ_SHEETS_SECRET';

var USERS_HEADER = ['chat_id', 'bucket', 'is_premium', 'messages', 'cta_shown', 'source', 'seen_content', 'created_at'];
var EVENTS_HEADER = ['ts', 'chat_id', 'event', 'payload'];
var CONTENT_HEADER = ['message_id', 'tags', 'tier', 'title'];

function doPost(e) {
  try {
    var payload = JSON.parse(e.postData.contents || '{}');
    var action = payload.action;

    // Секрет приходит в теле (новые вызовы) либо в query (легаси sheets_writer).
    var secret = payload.secret || e.parameter.secret;
    if (secret !== SECRET) {
      return json_({ error: 'forbidden' });
    }
    delete payload.secret;

    // Обратная совместимость: старый вызов из utils/sheets_writer.py
    if (!action) {
      return handleOrder_(payload);
    }

    switch (action) {
      case 'users_all':      return json_(readAll_('users', USERS_HEADER));
      case 'user_upsert':    return json_(upsertUser_(payload.user));
      case 'flush':          return json_(flush_(payload.users || [], payload.events || []));
      case 'content_all':    return json_(readAll_('content', CONTENT_HEADER));
      case 'content_upsert': return json_(upsertContent_(payload.item));
      case 'content_bulk':   return json_(bulkContent_(payload.items || []));
      case 'content_delete': return json_(deleteContent_(payload.message_id));
      default:               return json_({ error: 'unknown action: ' + action });
    }
  } catch (err) {
    return json_({ error: String(err) });
  }
}

/* ---------- helpers ---------- */

function json_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}

function sheet_(name, header) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.appendRow(header);
    sh.setFrozenRows(1);
  }
  return sh;
}

function readAll_(name, header) {
  var sh = sheet_(name, header);
  var values = sh.getDataRange().getValues();
  if (values.length < 2) return [];
  var keys = values[0];
  var out = [];
  for (var i = 1; i < values.length; i++) {
    var row = {};
    for (var c = 0; c < keys.length; c++) {
      row[keys[c]] = values[i][c];
    }
    out.push(row);
  }
  return out;
}

/** Карта значение_первой_колонки -> номер строки (1-based). */
function keyIndex_(sh) {
  var values = sh.getDataRange().getValues();
  var index = {};
  for (var i = 1; i < values.length; i++) {
    index[String(values[i][0])] = i + 1;
  }
  return index;
}

function writeRow_(sh, header, obj, rowNumber) {
  var row = header.map(function (key) {
    var v = obj[key];
    return v === undefined || v === null ? '' : v;
  });
  // chat_id и message_id пишем текстом, иначе Sheets съест длинные числа
  if (rowNumber) {
    sh.getRange(rowNumber, 1, 1, header.length).setValues([row]);
  } else {
    sh.appendRow(row);
  }
}

/* ---------- users ---------- */

function upsertUser_(user) {
  if (!user || !user.chat_id) return { error: 'no chat_id' };
  var sh = sheet_('users', USERS_HEADER);
  var index = keyIndex_(sh);
  writeRow_(sh, USERS_HEADER, user, index[String(user.chat_id)]);
  return { ok: true };
}

function flush_(users, events) {
  var written = 0;

  if (users.length) {
    var sh = sheet_('users', USERS_HEADER);
    var index = keyIndex_(sh);
    var appends = [];
    users.forEach(function (user) {
      if (!user || !user.chat_id) return;
      var rowNumber = index[String(user.chat_id)];
      if (rowNumber) {
        writeRow_(sh, USERS_HEADER, user, rowNumber);
      } else {
        appends.push(USERS_HEADER.map(function (k) {
          return user[k] === undefined || user[k] === null ? '' : user[k];
        }));
      }
      written++;
    });
    if (appends.length) {
      sh.getRange(sh.getLastRow() + 1, 1, appends.length, USERS_HEADER.length).setValues(appends);
    }
  }

  if (events.length) {
    var esh = sheet_('events', EVENTS_HEADER);
    var rows = events.map(function (ev) {
      return [
        ev.ts || '',
        ev.chat_id || '',
        ev.event || '',
        JSON.stringify(ev.payload || {})
      ];
    });
    esh.getRange(esh.getLastRow() + 1, 1, rows.length, EVENTS_HEADER.length).setValues(rows);
  }

  return { ok: true, users: written, events: events.length };
}

/* ---------- content ---------- */

function upsertContent_(item) {
  if (!item || !item.message_id) return { error: 'no message_id' };
  var sh = sheet_('content', CONTENT_HEADER);
  var index = keyIndex_(sh);
  writeRow_(sh, CONTENT_HEADER, item, index[String(item.message_id)]);
  return { ok: true };
}

function bulkContent_(items) {
  items.forEach(function (item) { upsertContent_(item); });
  return { ok: true, count: items.length };
}

function deleteContent_(messageId) {
  var sh = sheet_('content', CONTENT_HEADER);
  var rowNumber = keyIndex_(sh)[String(messageId)];
  if (rowNumber) sh.deleteRow(rowNumber);
  return { ok: true };
}
