const images = ["/images/ssssource.jpg", "/images/ssssource2.jpg", "/images/ssssource3.jpg", "/images/ssssource4.jpg", "/images/ssssource5.jpg"];
let currentIndex = 0;

function changeImage() {
    const imgElement = document.getElementById("slideshow");
    imgElement.src = images[currentIndex];
    currentIndex = (currentIndex + 1) % images.length;
}

setInterval(changeImage, 10000);

setTimeout(() => {
    document.querySelectorAll('.alert').forEach(el => {
        el.style.opacity = '0';
        setTimeout(() => el.remove(), 1000);
    });
}, 5000);
