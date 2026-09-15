// 기존 utils.js는 이제 두 개의 모듈로 분리되었습니다.
// 하위 호환성을 위해 여기서는 새로운 모듈들을 다시 내보냅니다.
// 새로운 코드에서는 core/js/utils/core.js 와 infrastructure/azure/js/storage-utils.js 를 직접 사용하세요.

const core = require("../../utils/core");
const storage = require("../../../infrastructure/azure/js/storage-utils");

module.exports = {
    ...core,
    ...storage,
};