import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import QRCodeSvgLib from "qrcode-svg";

type PassInfo = { token: string; name: string; reference: string; branch: string; batch: string };

const esc = (s: string) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c] as string));

function passHtml(p: PassInfo) {
  const qr = new QRCodeSvgLib({ content: p.token, padding: 2, width: 260, height: 260, color: "#0B192C", background: "#FFFFFF", ecl: "M" }).svg();
  return `<!DOCTYPE html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
  @page { size: A5; margin: 12mm; }
  * { -webkit-print-color-adjust: exact; print-color-adjust: exact; box-sizing: border-box; }
  body { margin: 0; font-family: Georgia, 'Times New Roman', serif; background: #FDFBF7; }
  .t { width: 100%; max-width: 420px; margin: 0 auto; background: #0B192C; color: #FDFBF7; border: 2px solid #D4AF37; border-radius: 18px; padding: 28px; text-align: center; }
  .eb { color: #D4AF37; font: bold 10px Arial, sans-serif; letter-spacing: 4px; }
  h1 { font-size: 40px; margin: 6px 0 2px; font-weight: 700; }
  .tg { font: 11px Arial, sans-serif; letter-spacing: 6px; opacity: .85; }
  hr { border: 0; border-top: 1px solid rgba(212,175,55,.5); margin: 18px 0; }
  .qr { display: inline-block; background: #fff; padding: 14px; border-radius: 12px; }
  .ref { color: #D4AF37; font: bold 14px Arial, sans-serif; letter-spacing: 3px; margin-top: 12px; }
  table { width: 100%; margin-top: 16px; border-collapse: collapse; font-family: Arial, sans-serif; }
  td { padding: 6px 0; font-size: 13px; }
  td.l { color: #D4AF37; font-weight: bold; font-size: 10px; letter-spacing: 2px; text-align: left; }
  td.v { text-align: right; }
  .n { font: 11px Arial, sans-serif; opacity: .7; margin-top: 16px; }
</style></head><body>
<div class="t">
  <div class="eb">DELTA ACADEMY PRESENTS</div>
  <h1>OLAM 3.0</h1>
  <div class="tg">THE GRAND WEDDING</div>
  <hr/>
  <div class="qr">${qr}</div>
  <div class="ref">${esc(p.reference)}</div>
  <table>
    <tr><td class="l">GUEST</td><td class="v">${esc(p.name)}</td></tr>
    <tr><td class="l">BRANCH</td><td class="v">${esc(p.branch)}</td></tr>
    <tr><td class="l">BATCH</td><td class="v">${esc(p.batch)}</td></tr>
    <tr><td class="l">STATUS</td><td class="v">APPROVED</td></tr>
  </table>
  <div class="n">Show this pass (printed or on your phone) at the entrance. Each pass admits one guest, one time. Do not share it.</div>
</div></body></html>`;
}

/** Native: creates a PDF and opens the share sheet (save to Files / Drive / WhatsApp).
 *  Web: prints only the pass (hidden iframe) so "Save as PDF" captures the designed ticket. */
export async function savePassPdf(p: PassInfo) {
  const html = passHtml(p);
  if (Platform.OS === "web") {
    const frame = document.createElement("iframe");
    frame.style.cssText = "position:fixed;right:0;bottom:0;width:0;height:0;border:0;";
    document.body.appendChild(frame);
    const doc = frame.contentWindow!.document;
    doc.open(); doc.write(html); doc.close();
    await new Promise((r) => setTimeout(r, 300));
    frame.contentWindow!.focus();
    frame.contentWindow!.print();
    setTimeout(() => frame.remove(), 1000);
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Save your OLAM 3.0 pass", UTI: "com.adobe.pdf" });
  } else {
    await Print.printAsync({ uri });
  }
}
