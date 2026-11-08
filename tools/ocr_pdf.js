// macOS Vision OCR：把扫描版 PDF 转成文本（中文＋英文）。
// 用法：
//   PDF_PATH=/path/a.pdf OUT_PATH=/tmp/a.txt [MAX_PAGES=20] osascript -l JavaScript tools/ocr_pdf.js
// 说明：逐页渲染成 PNG 再交给 Vision 识别，约 1–2 秒/页；无第三方依赖，仅限 macOS。
ObjC.import('AppKit'); ObjC.import('Quartz'); ObjC.import('Vision');
function main() {
  var env = $.NSProcessInfo.processInfo.environment;
  var pdf = env.objectForKey('PDF_PATH').js;
  var out = env.objectForKey('OUT_PATH').js;
  var maxp = env.objectForKey('MAX_PAGES') ? parseInt(env.objectForKey('MAX_PAGES').js) : 0;
  var doc = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(pdf));
  if (!doc) { $.NSLog('打不开：' + pdf); return; }
  var end = maxp > 0 ? Math.min(maxp, doc.pageCount) : doc.pageCount;
  var text = '';
  for (var i = 0; i < end; i++) {
    var page = doc.pageAtIndex(i);
    var r = page.boundsForBox($.kPDFDisplayBoxMediaBox);
    var img = page.thumbnailOfSizeForBox($.NSMakeSize(r.size.width * 1.6, r.size.height * 1.6), $.kPDFDisplayBoxMediaBox);
    var rep = $.NSBitmapImageRep.imageRepWithData(img.TIFFRepresentation);
    var png = '/tmp/_ocr_page.png';
    rep.representationUsingTypeProperties($.NSPNGFileType, $()).writeToFileAtomically(png, true);
    var req = $.VNRecognizeTextRequest.alloc.init;
    req.recognitionLanguages = ['zh-Hans', 'en-US'];
    req.recognitionLevel = 0;
    req.usesLanguageCorrection = true;
    $.VNImageRequestHandler.alloc.initWithURLOptions($.NSURL.fileURLWithPath(png), $())
      .performRequestsError($.NSArray.arrayWithObject(req), null);
    var res = req.results;
    text += '\n----- 第' + (i + 1) + '页 -----\n';
    if (res) for (var k = 0; k < res.count; k++) {
      var c = res.objectAtIndex(k).topCandidates(1);
      if (c && c.count > 0) text += c.objectAtIndex(0).string.js + '\n';
    }
  }
  $.NSString.alloc.initWithUTF8String(text).writeToFileAtomicallyEncodingError(out, true, $.NSUTF8StringEncoding, null);
  $.NSLog(out + ' ' + text.length + ' 字（' + end + ' 页）');
}
main();
