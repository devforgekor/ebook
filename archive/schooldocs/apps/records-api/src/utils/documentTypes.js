function getCohortId(documentType, submittedYear) {
  return `${documentType}_${submittedYear}`;
}

module.exports = { getCohortId };
