// A zip file made by hand: every file stored as it is, none squeezed. No DOM and no library, so Node can test it. The page uses
// it for "Download all", so the writer gets one file instead of a run of downloads.
//
// makeZip([{name, text}], when) gives the bytes of the zip (a Uint8Array). Names and text are written as UTF-8, and the zip
// says so (general-purpose flag bit 11), so names with accents or other scripts open as written. `when` is the date stamped on
// every file (a Date, default now); a zip keeps local time with a two-second step, from 1980 to 2107.

const encoder = new TextEncoder();

const TABLE = (() => {
  const table = new Uint32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c >>> 0;
  }
  return table;
})();

// The CRC-32 a zip keeps for each file, as an unsigned number.
export function crc32(bytes) {
  let crc = 0xffffffff;
  for (let at = 0; at < bytes.length; at += 1) crc = TABLE[(crc ^ bytes[at]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

// A date as the two numbers a zip keeps: {time, day}.
export function dosDate(when) {
  const year = Math.min(2107, Math.max(1980, when.getFullYear()));
  return {
    time: (when.getHours() << 11) | (when.getMinutes() << 5) | (when.getSeconds() >> 1),
    day: ((year - 1980) << 9) | ((when.getMonth() + 1) << 5) | when.getDate(),
  };
}

export function makeZip(files, when = new Date()) {
  const { time, day } = dosDate(when);
  const seen = new Set();
  const parts = [];
  const directory = [];
  let offset = 0;
  const push = (bytes) => { parts.push(bytes); offset += bytes.length; };

  for (const file of files) {
    if (seen.has(file.name)) throw new Error(`Two files are called ${file.name}`);
    seen.add(file.name);
    const name = encoder.encode(file.name);
    const data = typeof file.text === "string" ? encoder.encode(file.text) : file.bytes;
    if (name.length > 0xffff) throw new Error("A file name is too long for a zip");
    const crc = crc32(data);

    const local = new DataView(new ArrayBuffer(30));
    local.setUint32(0, 0x04034b50, true);     // local file header
    local.setUint16(4, 20, true);             // needed to open: 2.0
    local.setUint16(6, 0x0800, true);         // names are UTF-8
    local.setUint16(8, 0, true);              // stored
    local.setUint16(10, time, true);
    local.setUint16(12, day, true);
    local.setUint32(14, crc, true);
    local.setUint32(18, data.length, true);   // size when stored
    local.setUint32(22, data.length, true);   // size when opened
    local.setUint16(26, name.length, true);
    local.setUint16(28, 0, true);             // no extra field

    const entry = new DataView(new ArrayBuffer(46));
    entry.setUint32(0, 0x02014b50, true);     // central directory entry
    entry.setUint16(4, 20, true);             // made by: 2.0
    entry.setUint16(6, 20, true);
    entry.setUint16(8, 0x0800, true);
    entry.setUint16(10, 0, true);
    entry.setUint16(12, time, true);
    entry.setUint16(14, day, true);
    entry.setUint32(16, crc, true);
    entry.setUint32(20, data.length, true);
    entry.setUint32(24, data.length, true);
    entry.setUint16(28, name.length, true);
    entry.setUint32(42, offset, true);        // where its local header starts
    directory.push(new Uint8Array(entry.buffer), name);

    push(new Uint8Array(local.buffer));
    push(name);
    push(data);
    if (offset > 0xffffffff) throw new Error("The files are too big for a zip");
  }

  const start = offset;
  directory.forEach(push);
  const end = new DataView(new ArrayBuffer(22));
  end.setUint32(0, 0x06054b50, true);         // end of central directory
  end.setUint16(8, files.length, true);       // entries on this disk
  end.setUint16(10, files.length, true);      // entries in all
  end.setUint32(12, offset - start, true);    // size of the directory
  end.setUint32(16, start, true);
  push(new Uint8Array(end.buffer));

  const out = new Uint8Array(offset);
  let at = 0;
  for (const part of parts) { out.set(part, at); at += part.length; }
  return out;
}
