/**
 * 初始化地圖
 * 此函式會在 Google Maps API 載入完成後自動執行（callback=initMap）
 */
function initMap() {
    // 預設位置：台北 101 大樓附近
    const defaultLocation = {
        lat: 25.033964,  // 緯度
        lng: 121.564468  // 經度
    };

    // 建立地圖物件並顯示在 #map 元素中
    const map = new google.maps.Map(document.getElementById("map"), {
        center: defaultLocation,  // 地圖中心點
        zoom: 13                   // 縮放層級（1=世界，20=街道）
    });

    // 建立標記（預設隱藏）
    const marker = new google.maps.Marker({
        map: map,
        position: defaultLocation,
        visible: false  // 初始隱藏標記
    });

    // 取得搜尋輸入框元素
    const input = document.getElementById("search-input");

    // 建立 Autocomplete（自動完成）元件
    // 使用 Google Places API 提供地點搜尋建議
    const autocomplete = new google.maps.places.Autocomplete(input, {
        // 指定要回傳的欄位
        fields: ["name", "formatted_address", "geometry", "place_id"],
        // 限制只搜尋台灣（country code: "tw"）
        componentRestrictions: { country: "tw" }
    });

    // 監聽使用者選擇地點的事件
    autocomplete.addListener("place_changed", () => {
        // 取得使用者選擇的地點物件
        const place = autocomplete.getPlace();

        // 檢查地點是否有有效的經緯度資料
        if (!place.geometry || !place.geometry.location) {
            alert("找不到這個地點的經緯度資料，請重新選擇。");
            return;
        }

        // 從地點物件取出經緯度
        const lat = place.geometry.location.lat();  // 緯度
        const lng = place.geometry.location.lng();  // 經度

        // 自動填入表單欄位
        document.getElementById("place_name").value = place.name || "";           // 地點名稱
        document.getElementById("address").value = place.formatted_address || ""; // 完整地址
        document.getElementById("latitude").value = lat;                          // 緯度
        document.getElementById("longitude").value = lng;                         // 經度
        document.getElementById("google_place_id").value = place.place_id || ""; // Google Place ID

        // 將地圖中心移到選中的地點
        map.setCenter({
            lat: lat,
            lng: lng
        });

        // 放大縮放層級（16 =  neighbourhood 級別）
        map.setZoom(16);

        // 移動標記到選中的位置並顯示
        marker.setPosition({
            lat: lat,
            lng: lng
        });

        marker.setVisible(true);
    });
}
