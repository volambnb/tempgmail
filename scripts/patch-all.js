const fs=require("fs");const path=require("path");const R=process.cwd();
function w(p,c){const f=path.join(R,p);fs.mkdirSync(path.dirname(f),{recursive:true});fs.writeFileSync(f,c);console.log("w",p);}
