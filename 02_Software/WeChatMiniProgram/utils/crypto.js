/**
 * 加密工具 — 纯 JS 实现（无外部依赖）
 * 
 * 提供:
 *   sha256(str) → hex 小写
 *   md5(str)    → hex 大写
 *   aes128cbcEncrypt(plaintext, key16, iv16) → base64
 * 
 * 用途: 移远云 OpenAPI 签名 + 密码加密
 */

// ==================== SHA-256 ====================

function sha256(message) {
  const K = [
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
    0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
    0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
    0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
  ];

  let bytes = utf8ToBytes(message);
  let bitLen = bytes.length * 8;

  // Padding: append 1, pad zeros, append 64-bit big-endian length
  bytes.push(0x80);
  while ((bytes.length % 64) !== 56) bytes.push(0x00);
  // 64-bit big-endian length (high 32 bits are always 0 for our message sizes)
  bytes.push(0, 0, 0, 0);
  bytes.push((bitLen >>> 24) & 0xff);
  bytes.push((bitLen >>> 16) & 0xff);
  bytes.push((bitLen >>> 8) & 0xff);
  bytes.push(bitLen & 0xff);

  let H = [0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];

  for (let i = 0; i < bytes.length; i += 64) {
    let w = new Array(64);
    for (let t = 0; t < 16; t++) {
      w[t] = (bytes[i+t*4] << 24) | (bytes[i+t*4+1] << 16) | (bytes[i+t*4+2] << 8) | bytes[i+t*4+3];
    }
    for (let t = 16; t < 64; t++) {
      let s0 = (rrot(w[t-15],7) ^ rrot(w[t-15],18) ^ (w[t-15]>>>3)) >>> 0;
      let s1 = (rrot(w[t-2],17) ^ rrot(w[t-2],19) ^ (w[t-2]>>>10)) >>> 0;
      w[t] = (w[t-16] + s0 + w[t-7] + s1) >>> 0;
    }

    let [a,b,c,d,e,f,g,h] = H;
    for (let t = 0; t < 64; t++) {
      let S1 = rrot(e,6) ^ rrot(e,11) ^ rrot(e,25);
      let ch = (e & f) ^ (~e & g);
      let T1 = (h + S1 + ch + K[t] + w[t]) >>> 0;
      let S0 = rrot(a,2) ^ rrot(a,13) ^ rrot(a,22);
      let maj = (a & b) ^ (a & c) ^ (b & c);
      let T2 = (S0 + maj) >>> 0;
      h = g; g = f; f = e; e = (d + T1) >>> 0;
      d = c; c = b; b = a; a = (T1 + T2) >>> 0;
    }
    H = [H[0]+a,H[1]+b,H[2]+c,H[3]+d,H[4]+e,H[5]+f,H[6]+g,H[7]+h].map(x=>x>>>0);
  }
  return H.map(x => x.toString(16).padStart(8,'0')).join('');
}

function rrot(n, k) { return (n >>> k) | (n << (32 - k)); }

// ==================== MD5 ====================

function md5(string) {
  function r(x, n) { return (x << n) | (x >>> (32 - n)); }

  let b = [];
  for (let i = 0; i < string.length; i++) b[i >> 2] |= string.charCodeAt(i) << ((i & 3) << 3);
  let n = string.length;
  b[n >> 2] |= 0x80 << ((n & 3) << 3);
  while ((b.length & 15) !== 14) b.push(0);
  b.push(n << 3);
  b.push(0);

  let [a0,b0,c0,d0] = [0x67452301,0xefcdab89,0x98badcfe,0x10325476];

  for (let k = 0; k < b.length; k += 16) {
    let [A,B,C,D] = [a0,b0,c0,d0];
    for (let i = 0; i < 64; i++) {
      let f, g;
      if (i < 16) { f = (B & C) | (~B & D); g = i; }
      else if (i < 32) { f = (D & B) | (~D & C); g = (5*i + 1) & 15; }
      else if (i < 48) { f = B ^ C ^ D; g = (3*i + 5) & 15; }
      else { f = C ^ (B | ~D); g = (7*i) & 15; }

      let tmp = D; D = C; C = B;
      B = (B + r(A + f + b[k + g] + MT[i], MS[i])) >>> 0;
      A = tmp;
    }
    a0 = (a0 + A) >>> 0; b0 = (b0 + B) >>> 0;
    c0 = (c0 + C) >>> 0; d0 = (d0 + D) >>> 0;
  }

  function w2b(w) { return [(w)&0xff,(w>>>8)&0xff,(w>>>16)&0xff,(w>>>24)&0xff]; }
  return [].concat(w2b(a0),w2b(b0),w2b(c0),w2b(d0))
    .map(function(x) { return x.toString(16).padStart(2,'0'); }).join('').toUpperCase();
}

const MS = [
  7,12,17,22,7,12,17,22,7,12,17,22,7,12,17,22,
  5,9,14,20,5,9,14,20,5,9,14,20,5,9,14,20,
  4,11,16,23,4,11,16,23,4,11,16,23,4,11,16,23,
  6,10,15,21,6,10,15,21,6,10,15,21,6,10,15,21
];
const MT = [];
for (let i = 0; i < 64; i++) MT[i] = Math.floor(4294967296 * Math.abs(Math.sin(i+1)));

// ==================== AES-128-CBC ====================

const SBOX = [
  0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
  0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
  0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
  0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
  0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
  0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
  0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
  0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
  0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
  0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
  0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
  0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
  0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
  0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
  0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
  0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
];

const RCON = [0x01,0x02,0x04,0x08,0x10,0x20,0x40,0x80,0x1b,0x36];

function aes128cbcEncrypt(plaintext, keyStr, ivStr) {
  const key = utf8ToBytes(keyStr);
  const iv = utf8ToBytes(ivStr);
  let data = utf8ToBytes(plaintext);

  // PKCS7 padding
  const pad = 16 - (data.length % 16);
  for (let i = 0; i < pad; i++) data.push(pad);

  // Key expansion
  const rk = keyExpansion(key);
  let prev = iv.slice();

  let result = [];
  for (let i = 0; i < data.length; i += 16) {
    let block = data.slice(i, i+16);
    for (let j = 0; j < 16; j++) block[j] ^= prev[j];
    block = aesEncryptBlock(block, rk);
    prev = block.slice();
    result = result.concat(block);
  }
  return bytesToBase64(result);
}

function keyExpansion(key) {
  let w = new Array(44);
  for (let i = 0; i < 4; i++) w[i] = [key[4*i], key[4*i+1], key[4*i+2], key[4*i+3]];
  for (let i = 4; i < 44; i++) {
    w[i] = [0,0,0,0];
    let t = w[i-1].slice();
    if (i%4 === 0) {
      t = [t[1],t[2],t[3],t[0]];
      for (let j = 0; j < 4; j++) t[j] = SBOX[t[j]];
      t[0] ^= RCON[i/4-1];
    }
    for (let j = 0; j < 4; j++) w[i][j] = w[i-4][j] ^ t[j];
  }
  let rk = [];
  for (let r = 0; r < 11; r++) {
    rk[r] = [];
    for (let j = 0; j < 4; j++) rk[r].push(w[r*4+j][0], w[r*4+j][1], w[r*4+j][2], w[r*4+j][3]);
  }
  return rk;
}

function aesEncryptBlock(block, rk) {
  let s = block.slice();
  addRoundKey(s, rk[0]);
  for (let r = 1; r < 10; r++) {
    subBytes(s); shiftRows(s); mixColumns(s); addRoundKey(s, rk[r]);
  }
  subBytes(s); shiftRows(s); addRoundKey(s, rk[10]);
  return s;
}

function subBytes(s) { for (let i=0;i<16;i++) s[i]=SBOX[s[i]]; }
function shiftRows(s) {
  [s[1],s[5],s[9],s[13]] = [s[5],s[9],s[13],s[1]];
  [s[2],s[6],s[10],s[14]] = [s[10],s[14],s[2],s[6]];
  [s[3],s[7],s[11],s[15]] = [s[15],s[3],s[7],s[11]];
}
function addRoundKey(s, k) { for (let i=0;i<16;i++) s[i]^=k[i]; }

function mixColumns(s) {
  for (let i=0;i<16;i+=4) {
    let a=s[i], b=s[i+1], c=s[i+2], d=s[i+3];
    s[i]   = gm(2,a)^gm(3,b)^c^d;
    s[i+1] = a^gm(2,b)^gm(3,c)^d;
    s[i+2] = a^b^gm(2,c)^gm(3,d);
    s[i+3] = gm(3,a)^b^c^gm(2,d);
  }
}
function gm(a,b) { let p=0; for(let i=0;i<8;i++){ if(b&1)p^=a; let hi=a&0x80; a=(a<<1)&0xff; if(hi)a^=0x1b; b>>=1; } return p; }

// ==================== 工具函数 ====================

function utf8ToBytes(str) {
  let bytes = [];
  for (let i = 0; i < str.length; i++) {
    let c = str.charCodeAt(i);
    if (c < 0x80) bytes.push(c);
    else if (c < 0x800) { bytes.push(0xc0|(c>>6), 0x80|(c&0x3f)); }
    else { bytes.push(0xe0|(c>>12), 0x80|((c>>6)&0x3f), 0x80|(c&0x3f)); }
  }
  return bytes;
}

function bytesToBase64(bytes) {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let result = '';
  for (let i = 0; i < bytes.length; i += 3) {
    let b1 = bytes[i], b2 = bytes[i+1] || 0, b3 = bytes[i+2] || 0;
    result += chars[b1>>2] + chars[((b1&3)<<4)|(b2>>4)];
    result += i+1 < bytes.length ? chars[((b2&15)<<2)|(b3>>6)] : '=';
    result += i+2 < bytes.length ? chars[b3&63] : '=';
  }
  return result;
}

// ==================== 登录专用组合函数 ====================

/**
 * 加密密码用于注册/登录
 * @param {string} pwd 明文密码
 * @param {string} random 16 位随机字符串
 * @returns {string} Base64 密文
 */
function encryptPassword(pwd, random) {
  const md5hash = md5(random);
  const aesKey = md5hash.substring(8, 24);
  const aesIv  = aesKey.substring(8) + aesKey.substring(0, 8);
  return aes128cbcEncrypt(pwd, aesKey, aesIv);
}

/**
 * 生成 16 位随机字符串
 */
function random16() {
  const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
  let r = '';
  for (let i = 0; i < 16; i++) r += chars[Math.floor(Math.random() * chars.length)];
  return r;
}

module.exports = { sha256, md5, aes128cbcEncrypt, encryptPassword, random16 };
