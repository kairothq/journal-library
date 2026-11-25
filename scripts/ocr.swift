import Vision
import AppKit
import Foundation
for path in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: path), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
  let req = VNRecognizeTextRequest(); req.recognitionLevel = .accurate; req.usesLanguageCorrection = true
  try? VNImageRequestHandler(cgImage: cg).perform([req])
  var out: [[String: Any]] = []
  for o in req.results ?? [] { if let c = o.topCandidates(1).first { let b = o.boundingBox
    out.append(["text": c.string, "conf": c.confidence, "x": b.minX, "y": 1-b.maxY, "w": b.width, "h": b.height]) } }
  let d = try! JSONSerialization.data(withJSONObject: ["file": (path as NSString).lastPathComponent, "lines": out])
  print(String(data: d, encoding: .utf8)!)
}
