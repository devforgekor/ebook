// js-utils | Shared Node.js utilities harvested from kuhwa & related projects
// needs: nodemailer (only for mailNotifier)
// modules: fetchAllPages(), mergeByKey(), staticFirstFetch(), sendFailureMail(), validatePattern()

module.exports = {
  ...require("./lib/paginate"),
  ...require("./lib/mergeByKey"),
  ...require("./lib/staticFirstFetch"),
  ...require("./lib/mailNotifier"),
  ...require("./lib/validateQueryParam"),
};
