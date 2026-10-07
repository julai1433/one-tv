ObjC.import('Foundation'); ObjC.import('CoreImage');
function run(argv) {
  var img = $.CIImage.imageWithContentsOfURL($.NSURL.fileURLWithPath(argv[0]));
  var det = $.CIDetector.detectorOfTypeContextOptions($.CIDetectorTypeQRCode, $(), $());
  var found = det.featuresInImage(img);
  return found.count > 0 ? found.objectAtIndex(0).messageString.js : "no se leyó";
}
