// main.js

// 在页面加载完成后执行
document.addEventListener('DOMContentLoaded', function() {
    // 处理Flash消息
    var flashMessage = document.getElementById('flash-message');
    if (flashMessage && flashMessage.textContent.trim()) {
        flashMessage.style.display = 'block';
        
        // 显示提示框
        alert(flashMessage.textContent.trim());
        
        // 3秒后自动隐藏消息
        setTimeout(function() {
            flashMessage.style.display = 'none';
        }, 3000);
    }
});