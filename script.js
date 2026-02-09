const images = ["ssssource.jpg", "ssssource2.jpg", "ssssource3.jpg", "ssssource4.jpg", "ssssource5.jpg"];
let currentIndex = 0;

function changeImage() {
    const imgElement = document.getElementById("slideshow");
    imgElement.src = images[currentIndex];
    currentIndex = (currentIndex + 1) % images.length;
}

setInterval(changeImage, 10000);