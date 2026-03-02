fetch("/slideshow-images").then(r => r.json()).then(images => {
  if (!images.length) images = ["/images/ssssource.jpg", "/images/ssssource2.jpg", "/images/ssssource3.jpg", "/images/ssssource4.jpg", "/images/ssssource5.jpg"];
  let i = 0;
  const el = document.getElementById("slideshow");
  setInterval(() => { el.src = images[i = (i+1) % images.length]; }, 10000);
}).catch(() => {
  const images = ["/images/ssssource.jpg", "/images/ssssource2.jpg", "/images/ssssource3.jpg", "/images/ssssource4.jpg", "/images/ssssource5.jpg"];
  let i = 0;
  const el = document.getElementById("slideshow");
  setInterval(() => { el.src = images[i = (i+1) % images.length]; }, 10000);
});

setTimeout(() => {
    document.querySelectorAll('.alert').forEach(el => {
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 1000);
    });
}, 5000);
